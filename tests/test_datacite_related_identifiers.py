"""Tests for the qualified references in the DataCite metadata.

The application knows two kinds of relation between published objects: the
version chain of a dataset, and the membership of a dataset in a collection.
Neither was expressed in the DOI record, see
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import pytest
from datacite import schema45
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        UserFactory)

from topobank_publication.doi_mixin import DOICreationMixin
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


def _publish(surface, user, authors):
    return Publication.publish(surface, "cc0-1.0", user, authors)


def _publishable_surface(user, name):
    surface = SurfaceFactory(created_by=user, name=name)
    Topography1DFactory(surface=surface)
    return surface


def _relations(metadata):
    """Return (relationType, relatedIdentifier) pairs of the metadata."""
    return [
        (entry["relationType"], entry["relatedIdentifier"])
        for entry in metadata["relatedIdentifiers"]
    ]


@pytest.fixture
def three_versions(db, example_authors, settings):
    """Three published versions of one dataset, each with a DOI."""
    settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = None

    user = UserFactory()
    surface = _publishable_surface(user, "Versioned dataset")

    versions = []
    for version in range(1, 4):
        publication = _publish(surface, user, example_authors)
        # DOI creation itself needs DataCite, so fake the minted name; only its
        # presence and value matter for the related identifiers.
        publication.doi_name = f"10.12345/ce-v{version}"
        publication.save()
        versions.append(publication)

    return versions


@pytest.mark.django_db
def test_single_version_has_no_related_versions(example_pub):
    assert example_pub.get_datacite_metadata(DOI_NAME)["relatedIdentifiers"] == []


@pytest.mark.django_db
def test_later_version_points_back_at_earlier_ones(three_versions):
    v1, v2, v3 = three_versions

    assert _relations(v3.get_datacite_metadata(DOI_NAME)) == [
        ("IsNewVersionOf", v1.doi_name),
        ("IsNewVersionOf", v2.doi_name),
    ]


@pytest.mark.django_db
def test_earlier_version_points_forward_at_later_ones(three_versions):
    v1, v2, v3 = three_versions

    assert _relations(v1.get_datacite_metadata(DOI_NAME)) == [
        ("IsPreviousVersionOf", v2.doi_name),
        ("IsPreviousVersionOf", v3.doi_name),
    ]


@pytest.mark.django_db
def test_middle_version_points_both_ways(three_versions):
    v1, v2, v3 = three_versions

    assert _relations(v2.get_datacite_metadata(DOI_NAME)) == [
        ("IsNewVersionOf", v1.doi_name),
        ("IsPreviousVersionOf", v3.doi_name),
    ]


@pytest.mark.django_db
def test_versions_without_doi_are_skipped(three_versions):
    v1, v2, v3 = three_versions
    v2.doi_name = ""
    v2.save()

    assert _relations(v3.get_datacite_metadata(DOI_NAME)) == [
        ("IsNewVersionOf", v1.doi_name),
    ]


@pytest.mark.django_db
def test_collection_and_members_reference_each_other(db, example_authors):
    user = UserFactory()
    publications = []
    for index, name in enumerate(["First dataset", "Second dataset"], start=1):
        publication = _publish(_publishable_surface(user, name), user, example_authors)
        publication.doi_name = f"10.12345/ce-p{index}"
        publication.save()
        publications.append(publication)

    collection = PublicationCollection.objects.create(
        title="A collection",
        publisher=user,
        unique_hash="test-hash",
        doi_name="10.12345/ce-coll-1",
    )
    collection.publications.set(publications)

    assert _relations(collection.get_datacite_metadata(DOI_NAME)) == [
        ("HasPart", "10.12345/ce-p1"),
        ("HasPart", "10.12345/ce-p2"),
    ]
    for publication in publications:
        assert _relations(publication.get_datacite_metadata(DOI_NAME)) == [
            ("IsPartOf", "10.12345/ce-coll-1"),
        ]


@pytest.mark.django_db
def test_collection_without_doi_is_not_referenced(db, example_authors):
    user = UserFactory()
    publication = _publish(
        _publishable_surface(user, "A dataset"), user, example_authors
    )
    collection = PublicationCollection.objects.create(
        title="A collection", publisher=user, unique_hash="test-hash"
    )
    collection.publications.set([publication])

    assert publication.get_datacite_metadata(DOI_NAME)["relatedIdentifiers"] == []


@pytest.mark.django_db
def test_related_identifiers_validate(three_versions):
    for publication in three_versions:
        assert schema45.validate(_kernel_metadata(publication))
