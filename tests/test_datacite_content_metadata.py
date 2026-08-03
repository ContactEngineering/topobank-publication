"""Tests for the data content descriptors in the DataCite metadata.

A DOI record which only describes the landing page gives no machine-readable
route to the data itself. FAIR assessment tools (e.g. F-UJI) therefore look for
a content identifier plus its format and size, see
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import pytest
from datacite import schema45
from django.conf import settings

from topobank_publication.doi_mixin import (CONTAINER_MIME_TYPE,
                                            METADATA_LANGUAGE,
                                            DOICreationMixin)

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
