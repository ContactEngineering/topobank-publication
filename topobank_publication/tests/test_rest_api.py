import pytest

from django.shortcuts import reverse

from topobank.manager.models import Surface, Topography

from ..models import Publication


@pytest.mark.django_db(transaction=True)
def test_delete_surface_routes(api_client, two_users, handle_usage_statistics):
    topo1, topo2, topo3 = Topography.objects.all()
    surface3 = topo3.surface

    # Delete of a published surface should always fail
    pub = Publication.publish(surface3, 'cc0', 'Bob')
    assert Surface.objects.count() == 3
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=pub.surface.id)))
    assert response.status_code == 403
    assert Surface.objects.count() == 3

    # Delete of a published surface should even fail for the owner
    api_client.force_authenticate(pub.surface.creator)
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=pub.surface.id)))
    assert response.status_code == 403
    assert Surface.objects.count() == 3
