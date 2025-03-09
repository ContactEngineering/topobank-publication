import pytest
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        TopographyAnalysisFactory, UserFactory)


@pytest.mark.django_db
@pytest.fixture
def test_instances(test_analysis_function):
    users = [UserFactory(username="user1"), UserFactory(username="user2")]

    surfaces = [
        SurfaceFactory(creator=users[0]),
        SurfaceFactory(creator=users[0]),
    ]

    topographies = [Topography1DFactory(surface=surfaces[0])]

    TopographyAnalysisFactory(
        function=test_analysis_function, subject_topography=topographies[0]
    )

    return users, surfaces, topographies
