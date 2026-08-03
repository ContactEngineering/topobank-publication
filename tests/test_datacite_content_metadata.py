"""Tests for the data content descriptors in the DataCite metadata.

A DOI record which only describes the landing page gives no machine-readable
route to the data itself. FAIR assessment tools (e.g. F-UJI) therefore look for
a content identifier plus its format and size, see
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import pytest
from datacite import schema45
from django.conf import settings
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        UserFactory)

from topobank_publication.doi_mixin import (CONTAINER_MIME_TYPE,
                                            METADATA_LANGUAGE,
                                            DOICreationMixin)
from topobank_publication.models import Publication

from .conftest import datacite_not_configured

DOI_NAME = "10.12345/ce-test"


@pytest.mark.django_db
def test_container_url_points_to_download_view(example_pub):
    assert example_pub.container_url == (
        f"{settings.PUBLICATION_URL_PREFIX}{example_pub.short_url}/download/"
    )


@pytest.mark.django_db
def test_metadata_contains_content_url(example_pub):
    metadata = example_pub.get_datacite_metadata(DOI_NAME)

    assert metadata["contentUrl"] == [example_pub.container_url]


@pytest.mark.django_db
def test_metadata_contains_format_and_language(example_pub):
    metadata = example_pub.get_datacite_metadata(DOI_NAME)

    assert metadata["formats"] == [CONTAINER_MIME_TYPE]
    assert metadata["language"] == METADATA_LANGUAGE


@pytest.mark.django_db
def test_metadata_omits_size_while_container_is_missing(example_pub):
    """The container is built asynchronously, so its size is initially unknown.

    Reporting a wrong or zero size would be worse than reporting none.
    """
    assert example_pub.container_size is None
    assert "sizes" not in example_pub.get_datacite_metadata(DOI_NAME)


@pytest.mark.django_db
def test_metadata_reports_size_once_container_exists(example_pub):
    example_pub.renew_container()

    size = example_pub.container_size
    assert size > 0
    assert example_pub.get_datacite_metadata(DOI_NAME)["sizes"] == [f"{size} bytes"]


@pytest.mark.django_db
def test_container_size_survives_missing_file(example_pub):
    """A container which vanished from storage must not break DOI creation."""
    example_pub.container.name = f"{example_pub.storage_prefix}/does-not-exist.zip"

    assert example_pub.container_size is None


@pytest.mark.django_db
def test_metadata_still_validates_against_kernel_4(example_pub):
    """`contentUrl` is API-only and has to be excluded before validating.

    The kernel-4 schema sets "additionalProperties": false, so validating the
    metadata as-is would fail.
    """
    metadata = example_pub.get_datacite_metadata(DOI_NAME)

    assert not schema45.validate(metadata)
    assert schema45.validate(
        {
            key: value
            for key, value in metadata.items()
            if key not in DOICreationMixin.DATACITE_API_ONLY_ATTRIBUTES
        }
    )


@datacite_not_configured
@pytest.mark.django_db
def test_datacite_accepts_and_echoes_content_url(
    datacite_available, datacite_client, datacite_cleanup_registry, settings
):
    """`contentUrl` is outside the kernel-4 schema, so verify the API takes it.

    This is the only check that the attribute really survives the round trip to
    DataCite; everything else about it can be asserted offline.
    """
    settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None
    settings.PUBLICATION_DOI_MANDATORY = False

    user = UserFactory()
    surface = SurfaceFactory(created_by=user, name="Surface with content URL")
    Topography1DFactory(surface=surface)
    publication = Publication.publish(
        surface,
        "cc0-1.0",
        user,
        [
            {
                "first_name": "Test",
                "last_name": "Author",
                "orcid_id": "",
                "affiliations": [{"name": "Test University", "ror_id": ""}],
            }
        ],
    )

    publication.create_doi(force_draft=True)
    datacite_cleanup_registry.append(publication.doi_name)

    client, _ = datacite_client
    attributes = client.get_metadata(publication.doi_name)

    assert attributes["contentUrl"] == [publication.container_url]
    assert attributes["formats"] == [CONTAINER_MIME_TYPE]
    assert attributes["language"] == METADATA_LANGUAGE
