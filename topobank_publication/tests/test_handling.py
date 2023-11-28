import datetime
import os.path
import yaml
import zipfile
from pathlib import Path
from io import BytesIO

import pytest
from pytest import approx

from django.shortcuts import reverse
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.text import slugify
from rest_framework.test import APIRequestFactory

from trackstats.models import Metric, Period

from .utils import FIXTURE_DIR, SurfaceFactory, Topography1DFactory, Topography2DFactory, UserFactory, two_topos, \
    one_line_scan, upload_file
from ..models import Topography, Surface, MAX_LENGTH_DATAFILE_FORMAT
from ..views import DEFAULT_CONTAINER_FILENAME

from topobank.utils import assert_in_content, \
    assert_redirects, assert_no_form_errors, assert_form_error


@pytest.mark.django_db
def test_usage_of_cached_container_on_download_of_published_surface(client, example_pub, mocker,
                                                                    handle_usage_statistics):
    user = UserFactory()
    client.force_login(user)

    assert not example_pub.container.name

    surface = example_pub.surface

    # we don't need the correct container here, so we just return some fake data
    import topobank.manager.containers
    write_container_mock = mocker.patch('topobank.manager.views.write_surface_container', autospec=True)
    write_container_mock.return_value = BytesIO(b'Hello Test')

    def download_published():
        """Download published surface, returns HTTPResponse"""
        return client.get(reverse('manager:surface-download', kwargs=dict(surface_id=surface.id)), follow=True)

    #
    # first download
    #
    response = download_published()
    assert response.status_code == 200

    # now container has been set because write_container was called
    assert write_container_mock.called
    assert write_container_mock.call_count == 1
    assert example_pub.container is not None

    #
    # second download
    #
    response = download_published()
    assert response.status_code == 200

    # no extra call of write_container because it is a published surface
    assert write_container_mock.call_count == 1
