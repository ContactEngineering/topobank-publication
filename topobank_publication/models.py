import hashlib
import logging
import math
import os.path
from io import BytesIO
from typing import Literal, Optional, Union

import pydantic
from django.conf import settings
from django.db import models, transaction
from django.http.request import urljoin
from django.urls import reverse
from django.utils import timezone
from django.utils.http import quote
from pydantic import conlist, constr
from topobank.manager.models import Surface
from topobank.users.models import User

from .doi_mixin import PublicationCollectionDOIMixin, PublicationDOIMixin
from .utils import (AlreadyPublishedException, DOICreationException,
                    NewPublicationTooFastException, PublicationException,
                    PublicationsDisabledException, UnknownCitationFormat,
                    set_publication_permissions)

_log = logging.getLogger(__name__)

MAX_LEN_AUTHORS_FIELD = 512

CITATION_FORMAT_FLAVORS = ["html", "ris", "bibtex", "biblatex"]
DEFAULT_KEYWORDS = ["surface", "topography"]

_ror_regex = r"^0[a-z|0-9]{6}[0-9]{2}$"
_orcid_regex = r"^(\d{4}-){3}\d{3}(\d|X)$"


class Affiliation(pydantic.BaseModel):
    name: str
    # See: https://ror.org/
    ror_id: Optional[Union[Literal[""], constr(pattern=_ror_regex)]] = None


class Author(pydantic.BaseModel):
    first_name: str
    last_name: str
    # See: https://orcid.org/
    orcid_id: Optional[Union[Literal[""], constr(pattern=_orcid_regex)]] = None
    affiliations: list[Affiliation]


Authors = pydantic.RootModel[conlist(Author, min_length=1)]


class Publication(PublicationDOIMixin, models.Model):
    """Represents a publication of a digital surface twin."""

    class Meta:
        unique_together = ("original_surface", "version")
        db_table = (
            "publication_publication"  # This used to be part of core topobank app
        )

    LICENSE_CHOICES = [
        (k, settings.CC_LICENSE_INFOS[k]["option_name"])
        for k in ["cc0-1.0", "ccby-4.0", "ccbysa-4.0"]
    ]
    DOI_STATE_DRAFT = "draft"
    DOI_STATE_REGISTERED = "registered"
    DOI_STATE_FINDABLE = "findable"
    DOI_STATE_CHOICES = [
        (k, settings.PUBLICATION_DOI_STATE_INFOS[k]["description"])
        for k in [DOI_STATE_DRAFT, DOI_STATE_REGISTERED, DOI_STATE_FINDABLE]
    ]

    short_url = models.CharField(max_length=10, unique=True, null=True)
    surface = models.OneToOneField(
        Surface, on_delete=models.PROTECT, related_name="publication"
    )
    original_surface = models.ForeignKey(
        Surface,
        on_delete=models.PROTECT,
        # original surface can no longer be deleted once published
        null=True,
        related_name="derived_publications",
    )
    publisher = models.ForeignKey(User, on_delete=models.PROTECT)
    publisher_orcid_id = models.CharField(
        max_length=19, default=""
    )  # 16 digits including 3 dashes
    version = models.PositiveIntegerField(default=1)
    datetime = models.DateTimeField(auto_now_add=True)
    license = models.CharField(
        max_length=12, choices=LICENSE_CHOICES, blank=False, default=""
    )
    authors_json = models.JSONField(default=list)
    datacite_json = models.JSONField(default=dict)
    container = models.FileField(max_length=50, default="")
    doi_name = models.CharField(
        max_length=50, default=""
    )  # part of DOI which starts with 10.
    # if empty, the DOI has not been generated yet
    doi_state = models.CharField(max_length=10, choices=DOI_STATE_CHOICES, default="")

    def get_authors_string(self):
        """Return author names as comma-separated string in correct order."""
        return ", ".join(
            [f"{a['first_name']} {a['last_name']}" for a in self.authors_json]
        )

    def get_absolute_url(self):
        return reverse("publication:go", args=[self.short_url])

    def get_api_url(self):
        return reverse("publication:publication-api-detail", kwargs={"pk": self.pk})

    def get_full_url(self):
        """Return URL which should be used to permanently point to this publication.

        If the publication has a DOI, this will be it's URL, otherwise
        it's a URL pointing to this web app.
        """
        if self.has_doi:
            return self.doi_url
        else:
            return urljoin(settings.PUBLICATION_URL_PREFIX, self.short_url)

    def get_citation(self, flavor):
        if flavor not in CITATION_FORMAT_FLAVORS:
            raise UnknownCitationFormat(flavor)
        method_name = "_get_citation_as_" + flavor
        return getattr(self, method_name)()

    def _get_citation_as_html(self):
        s = "{authors}. ({year}). contact.engineering. <em>{surface.name} (Version {version})</em>."
        s += ' <a href="{publication_url}">{publication_url}</a>'
        s = s.format(
            authors=self.get_authors_string(),
            year=self.datetime.year,
            version=self.version,
            surface=self.surface,
            publication_url=self.get_full_url(),
        )
        return s

    def _get_citation_as_ris(self):
        # see http://refdb.sourceforge.net/manual-0.9.6/sect1-ris-format.html
        # or  https://en.wikipedia.org/wiki/RIS_(file_format)
        # or  https://web.archive.org/web/20120526103719/http://refman.com/support/risformat_intro.asp
        #     https://web.archive.org/web/20120717122530/http://refman.com/support/direct%20export.zip
        s = ""

        def add(key, value):
            nonlocal s
            s += f"{key}  - {value}\n"

        # Electronic citation / Website
        add("TY", "ELEC")
        # Title
        add("TI", f"{self.surface.name} (Version {self.version})")
        # Authors
        for author in self.get_authors_string().split(","):
            add("AU", author.strip())
        # Publication Year
        add("PY", format(self.datetime, "%Y/%m/%d/"))
        # URL
        add("UR", self.get_full_url())
        # Name of Database
        add("DB", "contact.engineering")

        # Notes
        add("N1", self.surface.description)

        # add keywords, defaults ones and tags
        for kw in DEFAULT_KEYWORDS:
            add("KW", kw)
        for t in self.surface.tags.all():
            add("KW", t.name)

        # End of record, must be empty and last tag
        add("ER", "")

        return s.strip()

    def _get_citation_as_bibtex(self):
        title = f"{self.surface.name} (Version {self.version})"
        shortname = f"{self.surface.name}_v{self.version}".lower().replace(" ", "_")
        keywords = ",".join(DEFAULT_KEYWORDS)
        if self.surface.tags.count() > 0:
            keywords += "," + ",".join(t.name for t in self.surface.tags.all())

        s = """
        @misc{{
            {shortname},
            title  = {{{title}}},
            author = {{{author}}},
            year   = {{{year}}},
            note   = {{{note}}},
            keywords = {{{keywords}}},
            howpublished = {{{publication_url}}},
        }}
        """.format(
            title=title,
            author=self.get_authors_string().replace(", ", " and "),
            year=self.datetime.year,
            note=self.surface.description,
            publication_url=self.get_full_url(),
            keywords=keywords,
            shortname=shortname,
        )

        return s.strip()

    def _get_citation_as_biblatex(self):
        shortname = f"{self.surface.name}_v{self.version}".lower().replace(" ", "_")
        keywords = ",".join(DEFAULT_KEYWORDS)
        if self.surface.tags.count() > 0:
            keywords += "," + ",".join(t.name for t in self.surface.tags.all())

        s = """
        @online{{
            {shortname},
            title  = {{{title}}},
            version = {{{version}}},
            author = {{{author}}},
            year   = {{{year}}},
            month  = {{{month}}},
            date   = {{{date}}},
            note   = {{{note}}},
            keywords = {{{keywords}}},
            url = {{{url}}},
            urldate = {{{urldate}}}
        }}
        """.format(
            title=self.surface.name,
            version=self.version,
            author=self.get_authors_string().replace(", ", " and "),
            year=self.datetime.year,
            month=self.datetime.month,
            date=format(self.datetime, "%Y-%m-%d"),
            note=self.surface.description,
            url=self.get_full_url(),
            urldate=format(timezone.now(), "%Y-%m-%d"),
            keywords=keywords,
            shortname=shortname,
        )

        return s.strip()

    @property
    def storage_prefix(self):
        """Return prefix used for storage.
        https://docs.djangoproject.com/en/2.2/ref/models/fields/#django.db.models.FileField.upload_to
        Looks like a relative path to a directory.
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        return "publications/{}".format(self.short_url)

    @property
    def container_storage_path(self):
        """Return relative path of container in storage."""
        return f"{self.storage_prefix}/ce-{self.short_url}.zip"

    @property
    def doi_url(self):
        """Return DOI as URL string or return None if DOI hasn't been generated yet."""
        # This depends on in which state the DOI -
        # this is useful in development of DOIs are in "draft" mode
        if self.doi_name == "":
            return None
        elif self.doi_state == Publication.DOI_STATE_DRAFT:
            return urljoin(
                "https://doi.test.datacite.org/dois/", quote(self.doi_name, safe="")
            )
        else:
            return f"https://doi.org/{self.doi_name}"  # here we keep the slash

    @property
    def has_doi(self):
        """Returns True, if this publication already has a doi."""
        return self.doi_name != ""

    @property
    def has_container(self):
        """Returns True, if this publication already has an non-empty container file."""
        return self.container != "" and self.container.size > 0

    def renew_container(self):
        """Renew container file or create it if not existent."""
        from topobank.manager.export_zip import export_container_zip

        container_bytes = BytesIO()
        _log.info(f"Preparing container for publication '{self.short_url}'..")
        export_container_zip(container_bytes, [self.surface])
        _log.info(
            f"Saving container for publication with URL {self.short_url} to storage for later.."
        )
        container_bytes.seek(0)  # rewind
        self.container.save(self.container_storage_path, container_bytes)
        _log.info("Done.")

    @staticmethod
    def publish(surface: Surface, license: str, publisher: User, authors: list[dict]):
        """
        Publish surface.

        An immutable copy is created along with a publication entry.
        The latter is returned.

        Parameters
        ----------
        surface : Surface
            The surface object to be published.
        license : str
            One of the keys of LICENSE_CHOICES.
        publisher : User
            The user who is publishing the surface.
        authors : list
            List of authors as list of dicts, where each dict has the
            form as in the example below. Will be saved as-is in JSON
            format and will be used for creating a DOI.

        Returns
        -------
        Publication
            The created publication object.

        Raises
        ------
        PublicationsDisabledException
            If publications are disabled in the settings.
        AlreadyPublishedException
            If the surface is already published.
        NewPublicationTooFastException
            If a new publication is attempted too soon after the last one.
        PublicationException
            If there is an error during the publication process.

        (Fictional) Example of a dict representing an author:

        {
            'first_name': 'Melissa Kathrin'
            'last_name': 'Miller',
            'orcid_id': '1234-1234-1234-1224',
            'affiliations': [
                {
                    'name': 'University of Westminster',
                    'ror_id': '04ycpbx82'
                },
                {
                    'name': 'New York University Paris',
                    'ror_id': '05mq03431'
                },
            ]
        }
        """
        if not settings.PUBLICATION_ENABLED:
            raise PublicationsDisabledException()

        if surface.is_published:
            raise AlreadyPublishedException()

        #
        # Get latest publication (if it exists)
        #
        latest_publication = (
            Publication.objects.filter(original_surface=surface)
            .order_by("version")
            .last()
        )

        #
        # We limit the publication rate
        #
        min_seconds = settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS
        if (latest_publication is not None) and (min_seconds is not None):
            delta_since_last_pub = timezone.now() - latest_publication.datetime
            delta_secs = delta_since_last_pub.total_seconds()
            if delta_secs < min_seconds:
                raise NewPublicationTooFastException(
                    latest_publication, math.ceil(min_seconds - delta_secs)
                )

        #
        # Validate license
        #
        license = license.lower()
        if license not in [x for x, y in Publication.LICENSE_CHOICES]:
            raise PublicationException(
                f"License '{license}' is not a valid choice for publication."
            )

        #
        # Validate authors
        #
        authors = Authors(authors)

        with transaction.atomic():
            #
            # Create a copy of this surface
            #
            copy = surface.deepcopy()

            try:
                set_publication_permissions(copy)
            except PublicationException:
                # see GH 704
                _log.error(
                    f"Could not set permission for copied surface to publish ... "
                    f"deleting copy (surface {copy.pk}) of surface {surface.pk}."
                )
                copy.delete()
                raise

            #
            # Create publication
            #
            if latest_publication:
                version = latest_publication.version + 1
            else:
                version = 1

            #
            # Save local reference for the publication
            #
            pub = Publication.objects.create(
                surface=copy,
                original_surface=surface,
                authors_json=authors.model_dump(),
                license=license,
                version=version,
                publisher=publisher,
                publisher_orcid_id=publisher.orcid_id,
            )

        #
        # Try to create DOI - if this doesn't work, rollback
        #
        if settings.PUBLICATION_DOI_MANDATORY:
            try:
                pub.create_doi()
            except DOICreationException as exc:
                _log.error("DOI creation failed, reason: %s", exc)
                _log.warning(
                    f"Cannot create publication with DOI, deleting copy (surface {copy.pk}) of "
                    f"surface {surface.pk} and publication instance."
                )
                pub.delete()  # need to delete pub first because it references copy
                copy.delete()
                raise PublicationException(f"Cannot create DOI, reason: {exc}") from exc
        else:
            _log.info(
                "Skipping creation of DOI, because it is not configured as mandatory."
            )

        _log.info(
            f"Published surface {surface.name} (id: {surface.id}) "
            + f"with license {license}, version {version}, authors '{authors}'"
        )
        _log.info(f"Direct URL of publication: {pub.get_absolute_url()}")
        _log.info(f"DOI name of publication: {pub.doi_name}")

        return pub

    def get_license_legalcode_filepath(self):
        return (
            f"{os.path.dirname(__file__)}/static/licenses/{self.license}-legalcode.txt"
        )


class PublicationCollection(PublicationCollectionDOIMixin, models.Model):
    title = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    short_url = models.CharField(max_length=10, unique=True, null=True)
    publications = models.ManyToManyField(
        Publication, related_name="publication_collection"
    )
    publisher = models.ForeignKey(User, on_delete=models.PROTECT)
    publisher_orcid_id = models.CharField(
        max_length=19, default=""
    )  # 16 digits including 3 dashes
    datetime = models.DateTimeField(auto_now_add=True)
    doi_name = models.CharField(
        max_length=50, default=""
    )  # part of DOI which starts with 10.
    # if empty, the DOI has not been generated yet
    doi_state = models.CharField(
        max_length=10, choices=Publication.DOI_STATE_CHOICES, default=""
    )
    datacite_json = models.JSONField(default=dict)
    unique_hash = models.CharField(max_length=64, unique=True, editable=False)

    @property
    def has_doi(self):
        """Returns True, if this publication already has a doi."""
        return self.doi_name != ""

    @property
    def doi_url(self):
        """Return DOI as URL string or return None if DOI hasn't been generated yet."""
        # This depends on in which state the DOI -
        # this is useful in development of DOIs are in "draft" mode
        if self.doi_name == "":
            return None
        elif self.doi_state == Publication.DOI_STATE_DRAFT:
            return urljoin(
                "https://doi.test.datacite.org/dois/", quote(self.doi_name, safe="")
            )
        else:
            return f"https://doi.org/{self.doi_name}"  # here we keep the slash

    def get_full_url(self):
        """Return URL which should be used to permanently point to this publication.

        If the publication has a DOI, this will be it's URL, otherwise
        it's a URL pointing to this web app.
        """
        if self.has_doi:
            return self.doi_url
        else:
            return urljoin(
                settings.PUBLICATION_URL_PREFIX, f"collection/{self.short_url}"
            )

    @staticmethod
    def publish(
        publications: list[Publication], title: str, description: str, publisher: User
    ):
        """
        Publish collection.

        An imutable collection of already published.

        Parameters
        ----------
        publications : list[publication]
            The publication to be bundled
        publisher : User
            The user who is publishing the surface.

        Returns
        -------
        PublicationCollection
            The created publication collection object.

        Raises
        ------
        PublicationsDisabledException
            If publications are disabled in the settings.
        AlreadyPublishedException
            If the publictions is already published.
        NewPublicationTooFastException
            If a new publication is attempted too soon after the last one.
        PublicationException
            If there is an error during the publication process.
        """
        if not settings.PUBLICATION_ENABLED:
            raise PublicationsDisabledException()

        """Generate a unique hash based on related model IDs."""
        ids = sorted([pub.id for pub in publications])
        hash_str = ",".join(
            map(str, ids)
        )  # Create a deterministic string representation

        unique_hash = hashlib.sha256(hash_str.encode()).hexdigest()
        if PublicationCollection.objects.filter(unique_hash=unique_hash).exists():
            raise AlreadyPublishedException()

        pub = PublicationCollection.objects.create(
            title=title,
            description=description,
            publisher=publisher,
            publisher_orcid_id=publisher.orcid_id,
            unique_hash=unique_hash,
        )
        pub.publications.set(publications)

        if settings.PUBLICATION_DOI_MANDATORY:
            try:
                pub.create_doi()
            except DOICreationException as exc:
                _log.error("DOI creation failed, reason: %s", exc)
                _log.warning("Cannot create DOI for publication collection")
                pub.delete()
                raise PublicationException(f"Cannot create DOI, reason: {exc}") from exc
        else:
            _log.info(
                "Skipping creation of DOI, because it is not configured as mandatory."
            )

        return pub
