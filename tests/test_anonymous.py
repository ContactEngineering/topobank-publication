import pytest
from django.shortcuts import reverse
from django.test import override_settings
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        UserFactory)
from topobank.testing.utils import assert_in_content

from topobank_publication.models import Publication


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
    surface = SurfaceFactory(created_by=bob, name=surface_name)
    Topography1DFactory(surface=surface)

    Publication.publish(surface, "cc0-1.0", surface.created_by, example_authors)

    # no one is logged in now, assuming the select tab sends a search request
    response = api_client.get(reverse("manager:surface-api-list"))

    # should see the published surface
    assert_in_content(response, surface_name)
