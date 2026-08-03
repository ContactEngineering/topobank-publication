"""
Tests for collapsing the published versions of a dataset in the dataset list.

Publishing creates a new `Surface`, so every version is a row of its own and the
same dataset used to appear several times in a search result, far apart and
distinguishable only by a small note (ContactEngineering/ce-ui#38). Only the
latest version is listed.

The collapsing itself lives in `topobank_rest_api.manager.filters`, but it can
only be exercised where the publication app is installed, which is here.
"""

import pytest
from rest_framework.reverse import reverse
from topobank.testing.factories import SurfaceFactory, Topography1DFactory

from topobank_publication.models import Publication


@pytest.fixture(autouse=True)
def _allow_repeated_publication(settings):
    """Publishing the same dataset twice in a row is rate-limited in production."""
    settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS = 0


def _publishable_surface(user, name):
    """A dataset that can be published: it needs one processed measurement."""
    surface = SurfaceFactory(name=name, created_by=user)
    Topography1DFactory(surface=surface)
    return surface


def _results(response):
    """The listed datasets, whether or not the response is paginated."""
    assert response.status_code == 200
    data = response.data
    return data["results"] if isinstance(data, dict) else data


def _listed_names(api_client, **query):
    response = api_client.get(reverse("manager:surface-api-list"), query)
    return [surface["name"] for surface in _results(response)]


def _listed_ids(api_client, **query):
    response = api_client.get(reverse("manager:surface-api-list"), query)
    return [surface["id"] for surface in _results(response)]


@pytest.mark.django_db
def test_only_the_latest_version_is_listed(api_client, example_authors):
    user = SurfaceFactory().created_by
    surface = _publishable_surface(user, "Ultrananocrystalline diamond")
    first = Publication.publish(surface, "cc0-1.0", user, example_authors)
    second = Publication.publish(surface, "cc0-1.0", user, example_authors)
    assert (first.version, second.version) == (1, 2)

    api_client.force_login(user)
    listed = _listed_ids(api_client)

    assert second.surface.id in listed
    assert first.surface.id not in listed


@pytest.mark.django_db
def test_the_unpublished_original_keeps_its_row(api_client, example_authors):
    """A work in progress is nobody's older version."""
    user = SurfaceFactory().created_by
    surface = _publishable_surface(user, "Work in progress")
    Publication.publish(surface, "cc0-1.0", user, example_authors)

    api_client.force_login(user)
    assert surface.id in _listed_ids(api_client)


@pytest.mark.django_db
def test_a_dataset_published_once_is_listed(api_client, example_authors):
    user = SurfaceFactory().created_by
    surface = _publishable_surface(user, "Published once")
    publication = Publication.publish(surface, "cc0-1.0", user, example_authors)

    api_client.force_login(user)
    assert publication.surface.id in _listed_ids(api_client)


@pytest.mark.django_db
def test_unpublished_datasets_are_untouched(api_client):
    user = SurfaceFactory().created_by
    SurfaceFactory(name="One", created_by=user)
    SurfaceFactory(name="Two", created_by=user)

    api_client.force_login(user)
    listed = _listed_names(api_client)
    assert "One" in listed
    assert "Two" in listed


@pytest.mark.django_db
def test_versions_of_different_datasets_do_not_collapse_together(
    api_client, example_authors
):
    user = SurfaceFactory().created_by
    first = _publishable_surface(user, "First dataset")
    second = _publishable_surface(user, "Second dataset")
    first_publication = Publication.publish(first, "cc0-1.0", user, example_authors)
    second_publication = Publication.publish(second, "cc0-1.0", user, example_authors)

    api_client.force_login(user)
    listed = _listed_ids(api_client)
    assert first_publication.surface.id in listed
    assert second_publication.surface.id in listed


@pytest.mark.django_db
def test_ordering_still_applies(api_client, example_authors):
    """The collapsing runs before ordering, which reduces the queryset to a set of
    primary keys; ordering has to survive that."""
    user = SurfaceFactory().created_by
    surface = _publishable_surface(user, "Beta")
    Publication.publish(surface, "cc0-1.0", user, example_authors)
    SurfaceFactory(name="Alpha", created_by=user)

    api_client.force_login(user)
    names = _listed_names(api_client, order_by="name")
    assert names == sorted(names)


@pytest.mark.django_db
def test_search_finds_the_latest_version(api_client, example_authors):
    """The case from the issue: searching for a name that every version shares
    returns one hit, not one per version."""
    user = SurfaceFactory().created_by
    surface = _publishable_surface(user, "Ultrananocrystalline diamond (UNCD)")
    Publication.publish(surface, "cc0-1.0", user, example_authors)
    latest = Publication.publish(surface, "cc0-1.0", user, example_authors)

    api_client.force_login(user)
    listed = _listed_ids(
        api_client, search="Ultrananocrystalline", sharing_status="published"
    )
    assert listed == [latest.surface.id]


@pytest.mark.django_db
def test_the_listed_row_says_which_version_it_is(api_client, example_authors):
    """Collapsing the versions would otherwise hide them without a trace."""
    user = SurfaceFactory().created_by
    surface = _publishable_surface(user, "Versioned")
    Publication.publish(surface, "cc0-1.0", user, example_authors)
    latest = Publication.publish(surface, "cc0-1.0", user, example_authors)

    api_client.force_login(user)
    response = api_client.get(reverse("manager:surface-api-list"))
    rows = {row["id"]: row for row in _results(response)}

    assert rows[latest.surface.id]["version"] == 2
    assert rows[latest.surface.id]["nb_versions"] == 2


@pytest.mark.django_db
def test_an_unpublished_dataset_has_no_version(api_client):
    user = SurfaceFactory().created_by
    surface = SurfaceFactory(name="Work in progress", created_by=user)

    api_client.force_login(user)
    response = api_client.get(reverse("manager:surface-api-list"))
    row = {r["id"]: r for r in _results(response)}[surface.id]

    assert row["version"] is None
    assert row["nb_versions"] is None
