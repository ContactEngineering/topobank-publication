import pytest
from django.shortcuts import reverse

from topobank.users.tests.factories import UserFactory
from topobank.utils import assert_in_content, assert_not_in_content
from topobank.manager.tests.utils import SurfaceFactory, Topography1DFactory
from topobank.manager.utils import selection_from_session, selection_to_instances


from ..models import Publication


@pytest.mark.django_db
def test_anonymous_user_can_see_published(api_client, handle_usage_statistics, example_authors):
    #
    # publish a surface
    #
    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    topo = Topography1DFactory(surface=surface)

    pub = Publication.publish(surface, 'cc0-1.0', example_authors)

    # no one is logged in now, assuming the select tab sends a search request
    response = api_client.get(reverse('manager:search'))

    # should see the published surface
    assert_in_content(response, surface_name)


@pytest.mark.django_db
def test_anonymous_user_can_select_published(client, handle_usage_statistics):
    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    topo = Topography1DFactory(surface=surface)
    pub = Publication.publish(surface, 'cc0-1.0', bob.name)
    published_surface = pub.surface
    published_topo = published_surface.topography_set.first()

    response = client.post(reverse('manager:topography-select', kwargs=dict(pk=published_topo.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_topos) == 1
    assert published_topo in sel_topos

    response = client.post(reverse('manager:topography-unselect', kwargs=dict(pk=published_topo.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_topos) == 0

    response = client.post(reverse('manager:surface-select', kwargs=dict(pk=published_surface.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_surfs) == 1
    assert published_surface in sel_surfs

    response = client.post(reverse('manager:surface-unselect', kwargs=dict(pk=published_surface.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_surfs) == 0
