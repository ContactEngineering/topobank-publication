import pytest
from django.shortcuts import reverse
from django.test import override_settings
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        UserFactory)
from topobank.testing.utils import assert_in_content

from ..models import Publication


@override_settings(DELETE_EXISTING_FILES=True)
@pytest.mark.django_db
def test_anonymous_user_can_see_published(
    api_client, handle_usage_statistics, example_authors
):
    #
    # publish a surface
    #
    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    Topography1DFactory(surface=surface)

    Publication.publish(surface, "cc0-1.0", surface.creator, example_authors)

    # no one is logged in now, assuming the select tab sends a search request
    response = api_client.get(f"{reverse('manager:surface-api-list')}?search_term={surface.name}")

    # should see the published surface
    assert_in_content(response, surface_name)
