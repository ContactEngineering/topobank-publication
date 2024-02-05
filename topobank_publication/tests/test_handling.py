from io import BytesIO

import pytest
from django.shortcuts import reverse
from topobank.manager.tests.utils import UserFactory


@pytest.mark.django_db
def test_usage_of_cached_container_on_download_of_published_surface(client, example_pub, mocker):
    user = UserFactory()
    client.force_login(user)

    assert not example_pub.container.name

    surface = example_pub.surface

    assert surface.is_published

    # we don't need the correct container here, so we just return some fake data
    write_container_mock = mocker.patch('topobank.manager.views.write_surface_container', autospec=True)
    write_container_mock.return_value = BytesIO(b'Hello Test')

    def download_published():
        """Download published surface, returns HTTPResponse"""
        return client.get(reverse('manager:surface-download', kwargs=dict(surface_id=surface.id)), follow=True)

    #
    # first download
    #
    response = download_published()
    assert response.status_code == 200, response.content

    # now container has been set because write_container was called
    assert write_container_mock.called
    assert write_container_mock.call_count == 1
    assert example_pub.container is not None

    #
    # second download
    #
    response = download_published()
    assert response.status_code == 200, response.content

    # no extra call of write_container because it is a published surface
    assert write_container_mock.call_count == 1
