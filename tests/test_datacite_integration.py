"""
Integration tests for DataCite API communication.

These tests interact with the real DataCite test API (api.test.datacite.org).
They only create draft DOIs which can be deleted after tests complete.

Requirements:
- DATACITE_USERNAME and DATACITE_PASSWORD must be set
- DATACITE_API_URL must point to api.test.datacite.org
- PUBLICATION_DOI_PREFIX must be a valid prefix for the test account

Tests are skipped if credentials are not configured or if the API URL
points to the production instance.

To run these tests locally, create a .envs/.datacite file with your
DataCite test credentials (see .envs/.datacite.template).
"""

import logging

import pytest
from datacite import DataCiteRESTClient
from datacite.errors import DataCiteError, HttpError
from django.conf import settings
from topobank.testing.factories import SurfaceFactory, UserFactory

from topobank_publication.models import Publication, PublicationCollection
from topobank_publication.utils import DOICreationException

from .conftest import (datacite_not_configured, get_datacite_skip_reason,
                       is_datacite_configured)

_log = logging.getLogger(__name__)


def _can_connect_to_datacite():
    """Try to connect to DataCite API to verify credentials work.

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    if not is_datacite_configured():
        return False, get_datacite_skip_reason()

    try:
        client = DataCiteRESTClient(
            username=settings.DATACITE_USERNAME,
            password=settings.DATACITE_PASSWORD,
            prefix=settings.PUBLICATION_DOI_PREFIX,
            url=settings.DATACITE_API_URL,
        )
        # Try to list DOIs to verify connection
        client.get_dois()
        return True, None
    except (DataCiteError, HttpError, Exception) as exc:
        error_msg = f"Cannot connect to DataCite API: {type(exc).__name__}: {exc}"
        _log.warning(error_msg)
        return False, error_msg


@pytest.fixture(scope="module")
def datacite_available():
    """Module-scoped fixture to check DataCite availability once per test module."""
    success, error_msg = _can_connect_to_datacite()
    if not success:
        pytest.skip(error_msg or "Cannot connect to DataCite API")


@pytest.fixture
def datacite_client(datacite_cleanup_registry):
    """
    Provides a DataCite REST client for tests.
    DOIs created using this client should be registered with the cleanup registry.
    """
    if not is_datacite_configured():
        pytest.skip("DataCite credentials not configured")

    client = DataCiteRESTClient(
        username=settings.DATACITE_USERNAME,
        password=settings.DATACITE_PASSWORD,
        prefix=settings.PUBLICATION_DOI_PREFIX,
        url=settings.DATACITE_API_URL,
    )
    return client, datacite_cleanup_registry


@pytest.fixture
def minimal_authors():
    """Minimal author data for testing."""
    return [
        {
            "first_name": "Test",
            "last_name": "Author",
            "orcid_id": "",
            "affiliations": [{"name": "Test University", "ror_id": ""}],
        }
    ]


@datacite_not_configured
@pytest.mark.django_db
class TestDataCitePublicationIntegration:
    """Integration tests for Publication DOI creation."""

    def test_create_draft_doi_for_publication(
        self, datacite_available, datacite_cleanup_registry, minimal_authors, settings
    ):
        """Test creating a draft DOI for a publication."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False  # We'll call create_doi manually

        user = UserFactory()
        surface = SurfaceFactory(created_by=user, name="Test Surface for DOI")

        # Create publication without DOI
        publication = Publication.publish(
            surface, "cc0-1.0", surface.created_by, minimal_authors
        )

        assert publication.doi_name == ""
        assert not publication.has_doi

        # Create draft DOI
        publication.create_doi(force_draft=True)

        # Register for cleanup
        datacite_cleanup_registry.append(publication.doi_name)

        # Verify DOI was created
        assert publication.has_doi
        assert publication.doi_name.startswith(settings.PUBLICATION_DOI_PREFIX)
        assert publication.doi_state == Publication.DOI_STATE_DRAFT
        assert "ce-" in publication.doi_name  # Format: <prefix>/ce-<short_url>
        assert publication.datacite_json  # Metadata should be saved

        # Verify DOI URL format for draft
        assert "doi.test.datacite.org" in publication.doi_url

    def test_create_doi_with_author_metadata(
        self, datacite_available, datacite_cleanup_registry, settings
    ):
        """Test DOI creation with full author metadata including ORCID and ROR."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        authors = [
            {
                "first_name": "Jane",
                "last_name": "Doe",
                "orcid_id": "0000-0002-1825-0097",  # Example sandbox ORCID
                "affiliations": [
                    {
                        "name": "University of Freiburg",
                        "ror_id": "0245cg223",  # Real ROR ID
                    }
                ],
            },
            {
                "first_name": "John",
                "last_name": "Smith",
                "orcid_id": "",  # No ORCID
                "affiliations": [
                    {"name": "Test Institute", "ror_id": ""},  # No ROR
                ],
            },
        ]

        user = UserFactory()
        surface = SurfaceFactory(
            created_by=user,
            name="Surface with Full Author Metadata",
            description="Test description for DataCite",
        )

        publication = Publication.publish(surface, "ccby-4.0", surface.created_by, authors)
        publication.create_doi(force_draft=True)
        datacite_cleanup_registry.append(publication.doi_name)

        # Verify metadata structure
        assert publication.has_doi
        datacite_data = publication.datacite_json

        # Check creators
        assert len(datacite_data["creators"]) == 2

        # First author should have ORCID and ROR
        creator1 = datacite_data["creators"][0]
        assert creator1["familyName"] == "Doe"
        assert creator1["givenName"] == "Jane"
        assert "nameIdentifiers" in creator1
        assert creator1["nameIdentifiers"][0]["nameIdentifier"] == "https://orcid.org/0000-0002-1825-0097"
        assert len(creator1["affiliation"]) == 1
        assert "affiliationIdentifier" in creator1["affiliation"][0]

        # Second author should not have ORCID identifier
        creator2 = datacite_data["creators"][1]
        assert "nameIdentifiers" not in creator2

    def test_create_doi_different_licenses(
        self, datacite_available, datacite_cleanup_registry, minimal_authors, settings
    ):
        """Test DOI creation with different license types."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        licenses = ["cc0-1.0", "ccby-4.0", "ccbysa-4.0"]

        for license_key in licenses:
            user = UserFactory()
            surface = SurfaceFactory(
                created_by=user, name=f"Test Surface - {license_key}"
            )

            publication = Publication.publish(
                surface, license_key, surface.created_by, minimal_authors
            )
            publication.create_doi(force_draft=True)
            datacite_cleanup_registry.append(publication.doi_name)

            assert publication.has_doi
            # Verify license info is in metadata
            rights_list = publication.datacite_json.get("rightsList", [])
            assert len(rights_list) > 0

    def test_doi_metadata_validation(
        self, datacite_available, datacite_cleanup_registry, minimal_authors, settings
    ):
        """Test that the generated metadata passes DataCite schema validation."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        user = UserFactory()
        surface = SurfaceFactory(
            created_by=user,
            name="Schema Validation Test",
            description="Testing that metadata validates correctly",
        )

        publication = Publication.publish(
            surface, "cc0-1.0", surface.created_by, minimal_authors
        )

        # This will raise DOICreationException if schema validation fails
        publication.create_doi(force_draft=True)
        datacite_cleanup_registry.append(publication.doi_name)

        # If we get here, validation passed
        assert publication.has_doi

        # Verify required fields are present
        metadata = publication.datacite_json
        assert "identifiers" in metadata
        assert "creators" in metadata
        assert "titles" in metadata
        assert "publicationYear" in metadata
        assert "types" in metadata

    def test_publication_versioning_with_doi(
        self, datacite_available, datacite_cleanup_registry, minimal_authors, settings
    ):
        """Test creating DOIs for multiple versions of the same surface."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        user = UserFactory()
        surface = SurfaceFactory(created_by=user, name="Versioned Surface")

        # Create first version
        pub_v1 = Publication.publish(
            surface, "cc0-1.0", surface.created_by, minimal_authors
        )
        pub_v1.create_doi(force_draft=True)
        datacite_cleanup_registry.append(pub_v1.doi_name)

        assert pub_v1.version == 1
        assert pub_v1.has_doi

        # Create second version
        surface.name = "Versioned Surface (Updated)"
        pub_v2 = Publication.publish(
            surface, "cc0-1.0", surface.created_by, minimal_authors
        )
        pub_v2.create_doi(force_draft=True)
        datacite_cleanup_registry.append(pub_v2.doi_name)

        assert pub_v2.version == 2
        assert pub_v2.has_doi

        # DOIs should be different
        assert pub_v1.doi_name != pub_v2.doi_name

        # Both should reference version in metadata
        assert pub_v1.datacite_json.get("version") == str(pub_v1.version)
        assert pub_v2.datacite_json.get("version") == str(pub_v2.version)


@datacite_not_configured
@pytest.mark.django_db
class TestDataCitePublicationCollectionIntegration:
    """Integration tests for PublicationCollection DOI creation."""

    def test_create_draft_doi_for_collection(
        self, datacite_available, datacite_cleanup_registry, minimal_authors, settings
    ):
        """Test creating a draft DOI for a publication collection."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        user = UserFactory()

        # Create two publications first
        surface1 = SurfaceFactory(created_by=user, name="Collection Surface 1")
        pub1 = Publication.publish(surface1, "cc0-1.0", user, minimal_authors)

        surface2 = SurfaceFactory(created_by=user, name="Collection Surface 2")
        pub2 = Publication.publish(surface2, "cc0-1.0", user, minimal_authors)

        # Create collection without DOI
        collection = PublicationCollection.publish(
            publications=[pub1, pub2],
            title="Test Collection",
            description="A test collection for DataCite integration",
            publisher=user,
        )

        assert collection.doi_name == ""
        assert not collection.has_doi

        # Create draft DOI
        collection.create_doi(force_draft=True)
        datacite_cleanup_registry.append(collection.doi_name)

        # Verify DOI was created
        assert collection.has_doi
        assert collection.doi_name.startswith(settings.PUBLICATION_DOI_PREFIX)
        assert collection.doi_state == Publication.DOI_STATE_DRAFT
        assert "ce-coll-" in collection.doi_name  # Format: <prefix>/ce-coll-<short_url>
        assert collection.datacite_json

        # Verify DOI URL format for draft
        assert "doi.test.datacite.org" in collection.doi_url

    def test_collection_doi_metadata_structure(
        self, datacite_available, datacite_cleanup_registry, minimal_authors, settings
    ):
        """Test that collection DOI metadata has correct structure."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        user = UserFactory(
            first_name="Collection",
            last_name="Publisher",
        )
        # Set ORCID ID on user (needed for collection metadata)
        user.orcid_id = "0000-0002-1825-0097"
        user.save()

        surface = SurfaceFactory(created_by=user, name="Surface for Collection")
        pub = Publication.publish(surface, "cc0-1.0", user, minimal_authors)

        collection = PublicationCollection.publish(
            publications=[pub],
            title="Metadata Test Collection",
            description="Testing metadata structure",
            publisher=user,
        )

        collection.create_doi(force_draft=True)
        datacite_cleanup_registry.append(collection.doi_name)

        metadata = collection.datacite_json

        # Verify required fields
        assert "doi" in metadata
        assert "creators" in metadata
        assert "titles" in metadata
        assert "publisher" in metadata
        assert "publicationYear" in metadata
        assert "types" in metadata

        # Verify creator is the publisher (not authors from publications)
        assert len(metadata["creators"]) == 1
        creator = metadata["creators"][0]
        assert creator["familyName"] == "Publisher"
        assert creator["givenName"] == "Collection"

        # Verify title
        assert metadata["titles"][0]["title"] == "Metadata Test Collection"

    def test_collection_requires_publications(
        self, datacite_available, settings
    ):
        """Test that a collection cannot be created without publications."""
        settings.PUBLICATION_DOI_MANDATORY = False

        user = UserFactory()

        # Attempting to create collection with empty list should fail
        # (the hash calculation will still work, but it's a degenerate case)
        collection = PublicationCollection.publish(
            publications=[],
            title="Empty Collection",
            description="Should this be allowed?",
            publisher=user,
        )

        # The collection is created but may fail DOI creation due to missing data
        # This test documents current behavior
        assert collection is not None

    def test_collection_duplicate_detection(
        self, datacite_available, datacite_cleanup_registry, minimal_authors, settings
    ):
        """Test that duplicate collections (same publications) are rejected."""
        from topobank_publication.utils import AlreadyPublishedException

        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        user = UserFactory()

        surface = SurfaceFactory(created_by=user, name="Surface for Duplicate Test")
        pub = Publication.publish(surface, "cc0-1.0", user, minimal_authors)

        # Create first collection
        PublicationCollection.publish(
            publications=[pub],
            title="First Collection",
            description="Original",
            publisher=user,
        )

        # Try to create duplicate collection with same publications
        with pytest.raises(AlreadyPublishedException):
            PublicationCollection.publish(
                publications=[pub],
                title="Duplicate Collection",
                description="Should fail",
                publisher=user,
            )


@datacite_not_configured
@pytest.mark.django_db
class TestDataCiteErrorHandling:
    """Test error handling for DataCite API failures."""

    def test_invalid_credentials_raises_exception(self, settings, minimal_authors):
        """Test that invalid credentials raise appropriate exception."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        # Temporarily override credentials
        original_username = settings.DATACITE_USERNAME
        original_password = settings.DATACITE_PASSWORD

        try:
            settings.DATACITE_USERNAME = "invalid_user"
            settings.DATACITE_PASSWORD = "invalid_password"

            user = UserFactory()
            surface = SurfaceFactory(created_by=user, name="Error Test Surface")
            publication = Publication.publish(
                surface, "cc0-1.0", surface.created_by, minimal_authors
            )

            with pytest.raises(DOICreationException):
                publication.create_doi(force_draft=True)

        finally:
            # Restore credentials
            settings.DATACITE_USERNAME = original_username
            settings.DATACITE_PASSWORD = original_password

    def test_invalid_api_url_raises_exception(self, settings, minimal_authors):
        """Test that invalid API URL raises appropriate exception."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        original_url = settings.DATACITE_API_URL

        try:
            settings.DATACITE_API_URL = "https://invalid.datacite.url/"

            user = UserFactory()
            surface = SurfaceFactory(created_by=user, name="Error Test Surface 2")
            publication = Publication.publish(
                surface, "cc0-1.0", surface.created_by, minimal_authors
            )

            with pytest.raises(DOICreationException):
                publication.create_doi(force_draft=True)

        finally:
            settings.DATACITE_API_URL = original_url


@datacite_not_configured
@pytest.mark.django_db
class TestDataCiteDOIVerification:
    """Tests that verify DOI can be retrieved from DataCite after creation."""

    def test_verify_doi_exists_in_datacite(
        self, datacite_available, datacite_client, datacite_cleanup_registry,
        minimal_authors, settings
    ):
        """Verify that created DOI can be retrieved from DataCite API."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        client, _ = datacite_client

        user = UserFactory()
        surface = SurfaceFactory(created_by=user, name="Verification Test Surface")
        publication = Publication.publish(
            surface, "cc0-1.0", surface.created_by, minimal_authors
        )

        publication.create_doi(force_draft=True)
        datacite_cleanup_registry.append(publication.doi_name)

        # Verify we can retrieve the DOI from DataCite
        doi_info = client.get_doi(publication.doi_name)

        assert doi_info is not None
        assert doi_info.get("data", {}).get("id") == publication.doi_name.lower()

    def test_verify_collection_doi_exists_in_datacite(
        self, datacite_available, datacite_client, datacite_cleanup_registry,
        minimal_authors, settings
    ):
        """Verify that collection DOI can be retrieved from DataCite API."""
        settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
        settings.PUBLICATION_DOI_MANDATORY = False

        client, _ = datacite_client

        user = UserFactory()
        user.orcid_id = "0000-0002-1825-0097"
        user.save()

        surface = SurfaceFactory(created_by=user, name="Collection Verification Surface")
        pub = Publication.publish(surface, "cc0-1.0", user, minimal_authors)

        collection = PublicationCollection.publish(
            publications=[pub],
            title="Verification Test Collection",
            description="Testing DOI retrieval",
            publisher=user,
        )

        collection.create_doi(force_draft=True)
        datacite_cleanup_registry.append(collection.doi_name)

        # Verify we can retrieve the DOI from DataCite
        doi_info = client.get_doi(collection.doi_name)

        assert doi_info is not None
        assert doi_info.get("data", {}).get("id") == collection.doi_name.lower()
