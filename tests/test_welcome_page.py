import pytest
from django.shortcuts import reverse
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        TopographyAnalysisFactory, UserFactory)

from topobank_publication.models import Publication


@pytest.fixture
def test_instances(db, test_analysis_function):
    """Fixture providing test users, surfaces, and topographies."""
    users = [UserFactory(username="user1"), UserFactory(username="user2")]

    surfaces = [
        SurfaceFactory(created_by=users[0]),
        SurfaceFactory(created_by=users[0]),
    ]

    topographies = [Topography1DFactory(surface=surfaces[0])]

    TopographyAnalysisFactory(
        function=test_analysis_function, subject_topography=topographies[0]
    )

    return users, surfaces, topographies


@pytest.mark.django_db
def test_welcome_page_statistics(
    api_client, test_instances, orcid_socialapp, handle_usage_statistics
):
    (user_1, user_2), (surface_1, surface_2), (topography_1,) = test_instances
    surface_2.grant_permission(user_2)

    Publication.publish(
        surface_1,
        "cc0-1.0",
        surface_1.created_by,
        [{"first_name": "Issac", "last_name": "Newton", "affiliations": []}],
    )

    #
    # Test statistics if user_1 is authenticated
    #
    api_client.force_login(user_1)
    response = api_client.get(reverse("manager:statistics"))

    assert response.data["nb_surfaces"] == 3
    assert response.data["nb_surfaces_of_user"] == 3
    assert response.data["nb_topographies"] == 2
    assert response.data["nb_topographies_of_user"] == 2
    assert response.data["nb_surfaces_shared_with_user"] == 0

    response = api_client.get(reverse("analysis:statistics"))

    assert response.data["nb_analyses"] == 1

    api_client.logout()

    #
    # Test statistics if user_2 is authenticated
    #
    api_client.force_login(user_2)
    response = api_client.get(reverse("manager:statistics"))

    assert response.data["nb_surfaces"] == 3
    assert response.data["nb_surfaces_of_user"] == 2
    assert response.data["nb_topographies"] == 2
    assert response.data["nb_topographies_of_user"] == 1
    assert response.data["nb_surfaces_shared_with_user"] == 2

    response = api_client.get(reverse("analysis:statistics"))

    assert response.data["nb_analyses"] == 1

    api_client.logout()
