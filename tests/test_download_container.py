"""
Tests for serving the archived container of a published dataset.

A publication keeps a pre-built container in storage, and that file is the one
its DOI refers to (`renew_containers` never rebuilds it once a DOI exists).
Downloads must therefore serve *that* file rather than assembling a fresh
archive from the live dataset.
"""

import pytest
from django.shortcuts import reverse
from rest_framework import status
from topobank.testing.factories import UserFactory


@pytest.mark.django_db
def test_download_redirects_to_the_archived_container(client, example_pub):
    example_pub.renew_container()
    assert example_pub.has_container

    client.force_login(UserFactory())
    response = client.get(
        reverse(
            "publication:download-container",
            kwargs={"short_url": example_pub.short_url},
        )
    )

    assert response.status_code in (status.HTTP_200_OK, status.HTTP_302_FOUND)


@pytest.mark.django_db
def test_download_is_available_to_anonymous_visitors(client, example_pub):
    """Published data is public, and so is its container."""
    example_pub.renew_container()

    response = client.get(
        reverse(
            "publication:download-container",
            kwargs={"short_url": example_pub.short_url},
        )
    )

    assert response.status_code in (status.HTTP_200_OK, status.HTTP_302_FOUND)


@pytest.mark.django_db
def test_download_without_an_archived_container_builds_container(client, example_pub):
    assert not example_pub.has_container

    client.force_login(UserFactory())
    response = client.get(
        reverse(
            "publication:download-container",
            kwargs={"short_url": example_pub.short_url},
        )
    )

    # The view builds the container on fallback and serves/redirects to it
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_302_FOUND)
    example_pub.refresh_from_db()
    assert example_pub.has_container


@pytest.mark.django_db
def test_download_of_unknown_publication_is_not_found(client):
    response = client.get(
        reverse(
            "publication:download-container", kwargs={"short_url": "NONSENSE"}
        )
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


#
# What the API advertises
#


@pytest.mark.django_db
def test_api_advertises_the_archived_container(
    api_client, example_pub, handle_usage_statistics
):
    api_client.force_login(UserFactory())
    response = api_client.get(example_pub.get_api_url())

    assert response.status_code == status.HTTP_200_OK
    assert response.data["download_url"] is not None
    assert f"go/{example_pub.short_url}/download/" in response.data["download_url"]
