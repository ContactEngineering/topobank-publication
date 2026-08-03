"""Tests for the access rights in the DataCite metadata.

The license alone does not say whether the data can be obtained: FAIR
assessment tools look for a separate, machine-readable access condition and
explicitly ignore rights entries that look like a license, see
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import pytest
from datacite import schema45
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        UserFactory)

from topobank_publication.doi_mixin import OPEN_ACCESS_RIGHTS, DOICreationMixin
from topobank_publication.models import Publication, PublicationCollection

DOI_NAME = "10.12345/ce-test"


def _kernel_metadata(publication):
    """Return the metadata without the attributes the kernel schema forbids.

    `create_doi` validates the same subset: some attributes are accepted by the
    DataCite API but are not part of the kernel-4 schema, which does not allow
    additional properties.
    """
    return {
        key: value
        for key, value in publication.get_datacite_metadata(DOI_NAME).items()
        if key not in DOICreationMixin.DATACITE_API_ONLY_ATTRIBUTES
    }


def _rights_uris(metadata):
    return [entry.get("rightsUri") for entry in metadata["rightsList"]]


@pytest.mark.django_db
def test_publication_declares_open_access(example_pub):
    metadata = example_pub.get_datacite_metadata(DOI_NAME)

    assert OPEN_ACCESS_RIGHTS in metadata["rightsList"]
    assert "info:eu-repo/semantics/openAccess" in _rights_uris(metadata)


@pytest.mark.django_db
def test_license_is_kept_alongside_access_rights(example_pub):
    """The access condition must not displace the license."""
    metadata = example_pub.get_datacite_metadata(DOI_NAME)

    spdx_identifiers = [
        entry.get("rightsIdentifier")
        for entry in metadata["rightsList"]
        if "rightsIdentifier" in entry
    ]
    assert spdx_identifiers == ["CC0-1.0"]
    assert len(metadata["rightsList"]) == 2


@pytest.mark.django_db
def test_access_rights_use_a_standard_term_and_uri():
    """The value has to come from a recognized vocabulary, not free text."""
    assert OPEN_ACCESS_RIGHTS["rights"] == "openAccess"
    assert OPEN_ACCESS_RIGHTS["rightsUri"].startswith("info:eu-repo/semantics/")


@pytest.mark.django_db
def test_collection_declares_open_access(example_authors):
    user = UserFactory()
    publications = []
    for name in ["First dataset", "Second dataset"]:
        surface = SurfaceFactory(created_by=user, name=name)
        Topography1DFactory(surface=surface)
        publications.append(
            Publication.publish(surface, "cc0-1.0", user, example_authors)
        )

    collection = PublicationCollection.objects.create(
        title="A collection", publisher=user, unique_hash="test-hash"
    )
    collection.publications.set(publications)

    metadata = collection.get_datacite_metadata(DOI_NAME)

    assert OPEN_ACCESS_RIGHTS in metadata["rightsList"]


@pytest.mark.django_db
def test_metadata_with_access_rights_validates(example_pub):
    """The `info:` URI of the access condition has to pass schema validation."""
    assert schema45.validate(_kernel_metadata(example_pub))
