"""
Mixins for DOI creation functionality.

This module provides reusable DOI creation logic for publication models,
eliminating code duplication between Publication and PublicationCollection.
"""

import logging
from typing import Any, Dict

from datacite import DataCiteRESTClient, schema45
from datacite.errors import DataCiteError, HttpError
from django.conf import settings

from .utils import DOICreationException

_log = logging.getLogger(__name__)

# MIME type of the published container archive, as served by the download view.
CONTAINER_MIME_TYPE = "application/zip"

# Language of the descriptive metadata (titles, descriptions). The application
# is English-only, as is all of its guidance to authors.
METADATA_LANGUAGE = "en"

# Access rights of a published dataset, expressed with the OpenAIRE access
# rights vocabulary (https://guidelines.openaire.eu). Published datasets are
# world-readable without registration, embargo or any other condition.
#
# This is deliberately kept separate from the license: a license states what
# may be done with the data once obtained, access rights state whether and
# under which conditions it can be obtained at all. Tools which look for access
# conditions discard entries that look like a license.
OPEN_ACCESS_RIGHTS = {
    "rights": "openAccess",
    "rightsUri": "info:eu-repo/semantics/openAccess",
}


class DOICreationMixin:
    """
    Abstract mixin providing DOI creation functionality for publications.

    This mixin handles the complete DOI creation workflow:
    1. Building the DOI name
    2. Getting metadata from subclass
    3. Validating against DataCite schema
    4. Submitting to DataCite REST API
    5. Saving DOI information to the database

    Subclasses must implement:
    - get_doi_suffix(): Return the DOI suffix (e.g., "ce-xyz")
    - get_datacite_metadata(): Return the DataCite metadata dict
    - get_full_url(): Return the full publication URL

    The subclass must also have these fields:
    - short_url: str
    - doi_name: str
    - doi_state: str
    - datacite_json: JSONField
    - save(): method
    """

    # DOI state constants (from Publication model)
    DOI_STATE_DRAFT = "draft"
    DOI_STATE_REGISTERED = "registered"
    DOI_STATE_FINDABLE = "findable"

    # Attributes which the DataCite REST API accepts and exposes, but which are
    # not part of the DataCite kernel-4 metadata schema. The kernel-4 JSON
    # schema sets "additionalProperties": false, so these have to be excluded
    # before validating; they are still submitted to the API.
    #
    # `contentUrl` is what makes a DOI record point at the actual data (rather
    # than only at the landing page). FAIR assessment tools read it to locate
    # the data content, see https://schema.org/contentUrl.
    DATACITE_API_ONLY_ATTRIBUTES = ("contentUrl",)

    def get_doi_suffix(self) -> str:
        """
        Return the suffix for the DOI.

        Subclasses must implement this method.

        Returns
        -------
        str
            DOI suffix, e.g., 'ce-abc123' or 'ce-coll-xyz789'
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_doi_suffix()"
        )

    def get_datacite_metadata(self, doi_name: str) -> Dict[str, Any]:
        """
        Build and return DataCite metadata dictionary.

        Subclasses must implement this method.

        Parameters
        ----------
        doi_name : str
            The full DOI name (prefix/suffix), e.g., '10.82035/ce-abc123'

        Returns
        -------
        dict
            DataCite schema 4.5 compliant metadata
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_datacite_metadata()"
        )

    def get_full_url(self) -> str:
        """
        Return the full URL of the publication.

        Subclasses must implement this method.

        Returns
        -------
        str
            Full URL where the publication can be accessed
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_full_url()"
        )

    def create_doi(self, force_draft: bool = False) -> None:
        """
        Create DOI at DataCite using available information.

        This method orchestrates the complete DOI creation workflow:
        1. Constructs the DOI name from prefix and suffix
        2. Retrieves metadata from the subclass
        3. Validates metadata against DataCite schema 4.5
        4. Submits DOI to DataCite REST API
        5. Saves DOI information to the database

        Parameters
        ----------
        force_draft : bool, optional
            If True, the DOI state will be 'draft' and can be deleted later.
            If False, the system settings will be used, which could be either
            'draft', 'registered', or 'findable'. The latter two cannot be
            deleted.

        Raises
        ------
        DOICreationException
            If DOI creation fails for any reason. The error message provides
            details about what went wrong.
        """
        # Build DOI name from prefix and suffix
        doi_name = f"{settings.PUBLICATION_DOI_PREFIX}/{self.get_doi_suffix()}"

        # Get metadata from subclass
        data = self.get_datacite_metadata(doi_name)

        # Validate against DataCite schema, ignoring the attributes which are
        # API-only and therefore unknown to the kernel-4 schema
        if not schema45.validate(
            {
                key: value
                for key, value in data.items()
                if key not in self.DATACITE_API_ONLY_ATTRIBUTES
            }
        ):
            raise DOICreationException(
                "Given data does not validate according to DataCite Schema 4.5!"
            )

        # Determine DOI state
        requested_doi_state = (
            self.DOI_STATE_DRAFT if force_draft else settings.PUBLICATION_DOI_STATE
        )

        # Create and submit DOI to DataCite
        self._submit_to_datacite(doi_name, data, requested_doi_state)

        # Save DOI information to model
        self._save_doi_info(doi_name, data, requested_doi_state)

        _log.info(f"Done creating DOI for '{self.short_url}'.")

    def _submit_to_datacite(
        self, doi_name: str, data: Dict[str, Any], doi_state: str
    ) -> None:
        """
        Submit DOI to DataCite REST API.

        Parameters
        ----------
        doi_name : str
            Full DOI name (prefix/suffix)
        data : dict
            DataCite metadata
        doi_state : str
            Requested DOI state ('draft', 'registered', or 'findable')

        Raises
        ------
        DOICreationException
            If submission to DataCite fails
        """
        client_kwargs = {
            "username": settings.DATACITE_USERNAME,
            "password": settings.DATACITE_PASSWORD,
            "prefix": settings.PUBLICATION_DOI_PREFIX,
            "url": settings.DATACITE_API_URL,
        }

        # Tracks whether we may have created something remotely at DataCite by the
        # time an exception is raised. This lets callers decide whether it is safe
        # to roll back (delete the local record) without stranding a dead remote
        # DOI. It starts False and is flipped to True immediately before / after
        # any call that mutates remote DataCite state.
        remote_created = False

        try:
            _log.info(
                f"Connecting to DataCite REST API at {settings.DATACITE_API_URL} "
                f"for DOI prefix {settings.PUBLICATION_DOI_PREFIX}..."
            )
            rest_client = DataCiteRESTClient(**client_kwargs)
            pub_full_url = self.get_full_url()

            match doi_state:
                case self.DOI_STATE_DRAFT:
                    _log.info(
                        f"Creating draft DOI '{doi_name}' for '{self.short_url}' "
                        "without URL link..."
                    )
                    # If draft_doi() itself fails, nothing was created remotely and
                    # remote_created stays False (safe to roll back). Once it
                    # returns, a draft DOI exists remotely; a subsequent failure on
                    # update_url() is ambiguous, so mark remote_created=True.
                    rest_client.draft_doi(data, doi=doi_name)
                    remote_created = True
                    _log.info(
                        f"Linking draft DOI '{doi_name}' to URL {pub_full_url}..."
                    )
                    rest_client.update_url(doi=doi_name, url=pub_full_url)

                case self.DOI_STATE_REGISTERED:
                    _log.info(
                        f"Creating registered DOI '{doi_name}' for '{self.short_url}' "
                        f"linked to {pub_full_url}..."
                    )
                    # A registered DOI cannot be deleted. If this single call fails
                    # we cannot tell whether the DOI was created remotely, so treat
                    # it as possibly created (do not roll back).
                    remote_created = True
                    rest_client.private_doi(data, url=pub_full_url, doi=doi_name)

                case self.DOI_STATE_FINDABLE:
                    _log.info(
                        f"Creating findable DOI '{doi_name}' for '{self.short_url}' "
                        f"linked to {pub_full_url}..."
                    )
                    # A findable DOI cannot be deleted; same ambiguity as above.
                    remote_created = True
                    rest_client.public_doi(data, url=pub_full_url, doi=doi_name)

                case _:
                    # Unknown state is caught before any remote mutation.
                    raise DataCiteError(
                        f"Requested DOI state {doi_state} is unknown."
                    )

            _log.info("DOI submitted successfully.")

        except (DataCiteError, HttpError) as exc:
            msg = f"DOI creation failed, reason: {exc}"
            _log.error(msg)
            raise DOICreationException(msg, remote_created=remote_created) from exc

    def _save_doi_info(
        self, doi_name: str, data: Dict[str, Any], doi_state: str
    ) -> None:
        """
        Save DOI information to the model.

        Parameters
        ----------
        doi_name : str
            Full DOI name
        data : dict
            DataCite metadata
        doi_state : str
            DOI state
        """
        _log.info("Saving DOI information to database...")
        self.doi_name = doi_name
        self.doi_state = doi_state
        self.datacite_json = data
        self.save()


class PublicationDOIMixin(DOICreationMixin):
    """
    Mixin providing DOI creation for Publication model.

    This mixin implements the abstract methods from DOICreationMixin
    to provide Publication-specific metadata generation.
    """

    def get_doi_suffix(self) -> str:
        """Return DOI suffix for publications: 'ce-{short_url}'."""
        return f"ce-{self.short_url}"

    def get_datacite_metadata(self, doi_name: str) -> Dict[str, Any]:
        """
        Build DataCite metadata for a Publication.

        Includes:
        - Multiple authors with affiliations and ORCID IDs
        - Surface name as title
        - Configurable license
        - Version information
        - Surface description

        Parameters
        ----------
        doi_name : str
            Full DOI name

        Returns
        -------
        dict
            DataCite schema 4.5 compliant metadata
        """
        license_infos = settings.CC_LICENSE_INFOS[self.license]

        # Build creators from authors_json
        creators = self._build_creators_from_authors()

        metadata = {
            # Mandatory fields
            "doi": doi_name,
            "creators": creators,
            "titles": [{"title": self.surface.name}],
            "publisher": {"name": "contact.engineering"},
            "publicationYear": str(self.datetime.year),
            "types": {"resourceType": "Dataset", "resourceTypeGeneral": "Dataset"},
            # Descriptors of the data itself: where it can be downloaded, in
            # which format and how large it is. Without these, the DOI record
            # only describes the landing page and gives no machine-readable
            # route to the data.
            "contentUrl": [self.container_url],
            "formats": [CONTAINER_MIME_TYPE],
            "language": METADATA_LANGUAGE,
            # Recommended/Optional fields
            "subjects": self._get_common_subjects(),
            "dates": [{"dateType": "Submitted", "date": self.datetime.isoformat()}],
            "version": str(self.version),
            "relatedIdentifiers": self._build_related_identifiers(),
            "rightsList": [
                {
                    "rights": license_infos["title"],
                    "rightsUri": license_infos["legal_code_url"],
                    "schemeUri": "https://spdx.org/licenses/",
                    "rightsIdentifier": license_infos["spdx_identifier"],
                    "rightsIdentifierScheme": "SPDX",
                    "lang": "en",
                },
                OPEN_ACCESS_RIGHTS,
            ],
            "descriptions": [
                {
                    "descriptionType": "Abstract",
                    "description": self.surface.description,
                }
            ],
            "schemaVersion": "http://datacite.org/schema/kernel-4",
        }

        # The container is built asynchronously after publication, so its size
        # is usually not known yet when the DOI is minted. Report it whenever it
        # is available; regenerating the metadata later fills it in.
        container_size = self.container_size
        if container_size is not None:
            metadata["sizes"] = [f"{container_size} bytes"]

        return metadata

    def _build_related_identifiers(self) -> list:
        """
        Build the list of qualified references to related publications.

        Two kinds of relation are known to the application:

        - other versions of the same dataset, i.e. publications sharing the
          same original surface, and
        - the publication collections this publication belongs to.

        Publications and collections without a DOI are skipped: an unminted
        publication has no identifier to point at.

        Returns
        -------
        list
            List of DataCite relatedIdentifier dictionaries
        """
        related = []

        if self.original_surface_id is not None:
            other_versions = (
                self.__class__.objects.filter(
                    original_surface_id=self.original_surface_id
                )
                .exclude(pk=self.pk)
                .exclude(doi_name="")
                .order_by("version")
            )
            for other in other_versions:
                related.append(
                    {
                        "relatedIdentifier": other.doi_name,
                        "relatedIdentifierType": "DOI",
                        "relationType": (
                            "IsNewVersionOf"
                            if other.version < self.version
                            else "IsPreviousVersionOf"
                        ),
                        "resourceTypeGeneral": "Dataset",
                    }
                )

        collections = (
            self.publication_collection.exclude(doi_name="").order_by("pk").all()
        )
        for collection in collections:
            related.append(
                {
                    "relatedIdentifier": collection.doi_name,
                    "relatedIdentifierType": "DOI",
                    "relationType": "IsPartOf",
                    "resourceTypeGeneral": "Collection",
                }
            )

        return related

    def _build_creators_from_authors(self) -> list:
        """
        Build creators list from authors_json field.

        Returns
        -------
        list
            List of creator dictionaries with names, affiliations, and ORCID IDs
        """
        creators = []
        for author in self.authors_json:
            creator = {
                "name": f"{author['last_name']}, {author['first_name']}",
                "nameType": "Personal",
                "givenName": author["first_name"],
                "familyName": author["last_name"],
            }

            # Add affiliations with optional ROR IDs
            creator_affiliations = []
            for aff in author["affiliations"]:
                creator_aff = {"name": aff["name"]}
                if aff["ror_id"]:
                    creator_aff.update(
                        {
                            "schemeUri": "https://ror.org/",
                            "affiliationIdentifier": f"https://ror.org/{aff['ror_id']}",
                            "affiliationIdentifierScheme": "ROR",
                        }
                    )
                creator_affiliations.append(creator_aff)
            creator["affiliation"] = creator_affiliations

            # Add ORCID if available
            if author["orcid_id"]:
                creator["nameIdentifiers"] = [
                    {
                        "schemeUri": "https://orcid.org",
                        "nameIdentifierScheme": "ORCID",
                        "nameIdentifier": f"https://orcid.org/{author['orcid_id']}",
                    }
                ]

            creators.append(creator)

        return creators

    @staticmethod
    def _get_common_subjects() -> list:
        """
        Return common subjects used by both publication types.

        Returns
        -------
        list
            List of subject dictionaries
        """
        return [
            {
                "subject": "FOS: Materials engineering",
                "valueUri": "http://www.oecd.org/science/inno/38235147.pdf",
                "schemeUri": "http://www.oecd.org/science/inno",
                "subjectScheme": "Fields of Science and Technology (FOS)",
            }
        ]


class PublicationCollectionDOIMixin(DOICreationMixin):
    """
    Mixin providing DOI creation for PublicationCollection model.

    This mixin implements the abstract methods from DOICreationMixin
    to provide PublicationCollection-specific metadata generation.
    """

    def get_doi_suffix(self) -> str:
        """Return DOI suffix for collections: 'ce-coll-{short_url}'."""
        return f"ce-coll-{self.short_url}"

    def _build_related_identifiers(self) -> list:
        """
        Build qualified references to the publications this collection bundles.

        Members without a DOI are skipped, as they have no identifier to point
        at. A collection is immutable, so this list cannot go stale.

        Returns
        -------
        list
            List of DataCite relatedIdentifier dictionaries
        """
        return [
            {
                "relatedIdentifier": publication.doi_name,
                "relatedIdentifierType": "DOI",
                "relationType": "HasPart",
                "resourceTypeGeneral": "Dataset",
            }
            for publication in self.publications.exclude(doi_name="").order_by("pk")
        ]

    def get_datacite_metadata(self, doi_name: str) -> Dict[str, Any]:
        """
        Build DataCite metadata for a PublicationCollection.

        Includes:
        - Single publisher with ORCID ID
        - Collection title
        - Hardcoded CC0-1.0 license
        - No version or description fields

        Parameters
        ----------
        doi_name : str
            Full DOI name

        Returns
        -------
        dict
            DataCite schema 4.5 compliant metadata
        """
        license_infos = settings.CC_LICENSE_INFOS["cc0-1.0"]

        creator = {
            "name": f"{self.publisher.last_name}, {self.publisher.first_name}",
            "nameType": "Personal",
            "givenName": self.publisher.first_name,
            "familyName": self.publisher.last_name,
        }
        # Only emit an ORCID name identifier if the publisher actually has an
        # ORCID iD. Emitting "https://orcid.org/" with an empty/None id would
        # produce an invalid identifier that could be rejected by DataCite.
        publisher_orcid_id = getattr(self.publisher, "orcid_id", None)
        if publisher_orcid_id:
            creator["nameIdentifiers"] = [
                {
                    "schemeUri": "https://orcid.org",
                    "nameIdentifier": f"https://orcid.org/{publisher_orcid_id}",
                    "nameIdentifierScheme": "ORCID",
                }
            ]

        return {
            # Mandatory fields
            "doi": doi_name,
            "creators": [creator],
            "titles": [{"title": self.title}],
            "publisher": {"name": "contact.engineering"},
            "publicationYear": str(self.datetime.year),
            "types": {"resourceType": "Dataset", "resourceTypeGeneral": "Dataset"},
            # Recommended/Optional fields
            "subjects": PublicationDOIMixin._get_common_subjects(),
            "dates": [{"dateType": "Submitted", "date": self.datetime.isoformat()}],
            "relatedIdentifiers": self._build_related_identifiers(),
            "rightsList": [
                {
                    "rights": license_infos["title"],
                    "rightsUri": license_infos["legal_code_url"],
                    "schemeUri": "https://spdx.org/licenses/",
                    "rightsIdentifier": license_infos["spdx_identifier"],
                    "rightsIdentifierScheme": "SPDX",
                    "lang": "en",
                },
                OPEN_ACCESS_RIGHTS,
            ],
            "schemaVersion": "http://datacite.org/schema/kernel-4",
        }
