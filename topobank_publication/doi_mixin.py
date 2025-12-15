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

        # Validate against DataCite schema
        if not schema45.validate(data):
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
                    rest_client.draft_doi(data, doi=doi_name)
                    _log.info(
                        f"Linking draft DOI '{doi_name}' to URL {pub_full_url}..."
                    )
                    rest_client.update_url(doi=doi_name, url=pub_full_url)

                case self.DOI_STATE_REGISTERED:
                    _log.info(
                        f"Creating registered DOI '{doi_name}' for '{self.short_url}' "
                        f"linked to {pub_full_url}..."
                    )
                    rest_client.private_doi(data, url=pub_full_url, doi=doi_name)

                case self.DOI_STATE_FINDABLE:
                    _log.info(
                        f"Creating findable DOI '{doi_name}' for '{self.short_url}' "
                        f"linked to {pub_full_url}..."
                    )
                    rest_client.public_doi(data, url=pub_full_url, doi=doi_name)

                case _:
                    raise DataCiteError(
                        f"Requested DOI state {doi_state} is unknown."
                    )

            _log.info("DOI submitted successfully.")

        except (DataCiteError, HttpError) as exc:
            msg = f"DOI creation failed, reason: {exc}"
            _log.error(msg)
            raise DOICreationException(msg) from exc

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

        return {
            # Mandatory fields
            "doi": doi_name,
            "creators": creators,
            "titles": [{"title": self.surface.name}],
            "publisher": {"name": "contact.engineering"},
            "publicationYear": str(self.datetime.year),
            "types": {"resourceType": "Dataset", "resourceTypeGeneral": "Dataset"},
            # Recommended/Optional fields
            "subjects": self._get_common_subjects(),
            "dates": [{"dateType": "Submitted", "date": self.datetime.isoformat()}],
            "version": str(self.version),
            "rightsList": [
                {
                    "rights": license_infos["title"],
                    "rightsUri": license_infos["legal_code_url"],
                    "schemeUri": "https://spdx.org/licenses/",
                    "rightsIdentifier": license_infos["spdx_identifier"],
                    "rightsIdentifierScheme": "SPDX",
                    "lang": "en",
                }
            ],
            "descriptions": [
                {
                    "descriptionType": "Abstract",
                    "description": self.surface.description,
                }
            ],
            "schemaVersion": "http://datacite.org/schema/kernel-4",
        }

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

        return {
            # Mandatory fields
            "doi": doi_name,
            "creators": [
                {
                    "name": f"{self.publisher.last_name}, {self.publisher.first_name}",
                    "nameType": "Personal",
                    "givenName": self.publisher.first_name,
                    "familyName": self.publisher.last_name,
                    "nameIdentifiers": [
                        {
                            "schemeUri": "https://orcid.org",
                            "nameIdentifier": f"https://orcid.org/{self.publisher.orcid_id}",
                            "nameIdentifierScheme": "ORCID",
                        }
                    ],
                }
            ],
            "titles": [{"title": self.title}],
            "publisher": {"name": "contact.engineering"},
            "publicationYear": str(self.datetime.year),
            "types": {"resourceType": "Dataset", "resourceTypeGeneral": "Dataset"},
            # Recommended/Optional fields
            "subjects": PublicationDOIMixin._get_common_subjects(),
            "dates": [{"dateType": "Submitted", "date": self.datetime.isoformat()}],
            "rightsList": [
                {
                    "rights": license_infos["title"],
                    "rightsUri": license_infos["legal_code_url"],
                    "schemeUri": "https://spdx.org/licenses/",
                    "rightsIdentifier": license_infos["spdx_identifier"],
                    "rightsIdentifierScheme": "SPDX",
                    "lang": "en",
                }
            ],
            "schemaVersion": "http://datacite.org/schema/kernel-4",
        }
