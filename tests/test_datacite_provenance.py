"""Tests for the provenance information in the DataCite metadata.

The DOI record used to carry a single date, the submission date, and no
contributors. It therefore said when a dataset was published but nothing about
where the data came from, see
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import datetime

import pytest
from datacite import schema45
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        UserFactory)

from topobank_publication.doi_mixin import DOICreationMixin
from topobank_publication.models import Publication

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


def _dates(metadata):
    return {entry["dateType"]: entry["date"] for entry in metadata["dates"]}


@pytest.mark.django_db
def test_publication_date_is_reported_precisely(example_pub):
    """`publicationYear` alone is only a year; `Available` carries the date."""
    dates = _dates(example_pub.get_datacite_metadata(DOI_NAME))

    assert dates["Submitted"] == example_pub.datetime.isoformat()
    assert dates["Available"] == example_pub.datetime.isoformat()


@pytest.mark.django_db
def test_creation_date_is_that_of_the_original_dataset(example_pub):
    """A published dataset is a copy, so its own creation date is useless."""
    dates = _dates(example_pub.get_datacite_metadata(DOI_NAME))

    assert dates["Created"] == example_pub.original_surface.created_at.isoformat()


@pytest.mark.django_db
def test_measurement_dates_are_reported_as_a_single_date(db, example_authors):
    user = UserFactory()
    surface = SurfaceFactory(created_by=user, name="One measurement date")
    measured = datetime.date(2021, 4, 5)
    Topography1DFactory(surface=surface, measurement_date=measured)
    Topography1DFactory(surface=surface, measurement_date=measured)

    publication = Publication.publish(surface, "cc0-1.0", user, example_authors)

    assert _dates(publication.get_datacite_metadata(DOI_NAME))["Collected"] == (
        "2021-04-05"
    )


@pytest.mark.django_db
def test_measurement_dates_are_reported_as_an_interval(db, example_authors):
    user = UserFactory()
    surface = SurfaceFactory(created_by=user, name="Several measurement dates")
    Topography1DFactory(surface=surface, measurement_date=datetime.date(2021, 4, 5))
    Topography1DFactory(surface=surface, measurement_date=datetime.date(2019, 1, 31))
    Topography1DFactory(surface=surface, measurement_date=datetime.date(2020, 7, 9))

    publication = Publication.publish(surface, "cc0-1.0", user, example_authors)

    assert _dates(publication.get_datacite_metadata(DOI_NAME))["Collected"] == (
        "2019-01-31/2021-04-05"
    )


@pytest.mark.django_db
def test_measurements_without_a_date_are_not_reported(db, example_authors):
    user = UserFactory()
    surface = SurfaceFactory(created_by=user, name="No measurement date")
    Topography1DFactory(surface=surface, measurement_date=None)

    publication = Publication.publish(surface, "cc0-1.0", user, example_authors)

    assert "Collected" not in _dates(publication.get_datacite_metadata(DOI_NAME))


@pytest.mark.django_db
def test_measurements_without_a_date_do_not_narrow_the_interval(db, example_authors):
    user = UserFactory()
    surface = SurfaceFactory(created_by=user, name="Mixed measurement dates")
    Topography1DFactory(surface=surface, measurement_date=datetime.date(2019, 1, 31))
    Topography1DFactory(surface=surface, measurement_date=None)
    Topography1DFactory(surface=surface, measurement_date=datetime.date(2021, 4, 5))

    publication = Publication.publish(surface, "cc0-1.0", user, example_authors)

    assert _dates(publication.get_datacite_metadata(DOI_NAME))["Collected"] == (
        "2019-01-31/2021-04-05"
    )


@pytest.mark.django_db
def test_publisher_is_reported_as_data_curator(example_pub):
    contributors = example_pub.get_datacite_metadata(DOI_NAME)["contributors"]

    assert len(contributors) == 1
    contributor = contributors[0]
    assert contributor["contributorType"] == "DataCurator"
    assert contributor["familyName"] == example_pub.publisher.last_name
    assert contributor["givenName"] == example_pub.publisher.first_name
    assert contributor["nameIdentifiers"][0]["nameIdentifier"] == (
        f"https://orcid.org/{example_pub.publisher_orcid_id}"
    )


@pytest.mark.django_db
def test_publisher_without_orcid_has_no_name_identifier(example_pub):
    example_pub.publisher_orcid_id = ""

    contributor = example_pub.get_datacite_metadata(DOI_NAME)["contributors"][0]

    assert "nameIdentifiers" not in contributor


@pytest.mark.django_db
def test_provenance_metadata_validates(example_pub):
    assert schema45.validate(_kernel_metadata(example_pub))


@pytest.mark.django_db
def test_provenance_metadata_with_interval_validates(db, example_authors):
    user = UserFactory()
    surface = SurfaceFactory(created_by=user, name="Interval validates")
    Topography1DFactory(surface=surface, measurement_date=datetime.date(2019, 1, 31))
    Topography1DFactory(surface=surface, measurement_date=datetime.date(2021, 4, 5))

    publication = Publication.publish(surface, "cc0-1.0", user, example_authors)

    assert schema45.validate(_kernel_metadata(publication))
