import pytest

from django.shortcuts import reverse

from topobank.manager.models import Surface, Topography

from ..models import Publication


@pytest.mark.django_db
def test_delete_surface_routes(api_client, two_users, handle_usage_statistics):
    topo1, topo2, topo3 = Topography.objects.all()
    surface3 = topo3.surface

    # Delete of a published surface should always fail
    pub = Publication.publish(surface3, 'cc0', 'Bob')
    assert Surface.objects.count() == 4
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=pub.surface.id)))
    assert response.status_code == 403
    assert Surface.objects.count() == 4

    # Delete of a published surface should even fail for the owner
    api_client.force_authenticate(pub.surface.creator)
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=pub.surface.id)))
    assert response.status_code == 403
    assert Surface.objects.count() == 4


@pytest.mark.django_db
def test_patch_topography_routes(api_client, two_users, handle_usage_statistics):
    user1, user2 = two_users
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo1.creator == user1

    new_name = 'My third new name'

    # Patch of a published surface should always fail
    pub = Publication.publish(topo3.surface, 'cc0', 'Bob')
    topo_pub, = pub.surface.topography_set.all()
    assert Topography.objects.count() == 4
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo_pub.id)),
                                {'name': new_name})
    assert response.status_code == 403  # The user can see the surface but not patch it, hence 403
    assert Surface.objects.count() == 4

    # Delete of a published surface should even fail for the owner
    api_client.force_authenticate(pub.surface.creator)
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo_pub.id)),
                                {'name': new_name})
    assert response.status_code == 403  # The user can see the surface but not patch it, hence 403
    assert Surface.objects.count() == 4
