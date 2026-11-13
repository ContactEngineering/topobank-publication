"""
Tests for serving the archived container of a published dataset.

A publication keeps a pre-built container in storage, and that file is the one
its DOI refers to (`renew_containers` never rebuilds it once a DOI exists).
Downloads must therefore serve *that* file rather than assembling a fresh
archive from the live dataset.
"""

import pytest
from django.core import mail
from django.core.cache import cache
from django.core.files.storage import default_storage
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
# Data that is missing from storage
#


def _download(client, pub):
    return client.get(
        reverse("publication:download-container", kwargs={"short_url": pub.short_url})
    )


@pytest.fixture
def pub_with_lost_datafile(example_pub, settings):
    """A publication one of whose data files was deleted from storage."""
    settings.ADMINS = [("Admin", "admin@example.com")]
    cache.clear()
    datafile = example_pub.surface.topography_set.first().datafile
    default_storage.delete(datafile.file.name)
    yield example_pub
    cache.clear()


@pytest.mark.django_db
def test_download_with_missing_datafile_is_unavailable_and_reported(
    client, pub_with_lost_datafile
):
    pub = pub_with_lost_datafile
    assert not pub.has_container

    response = _download(client, pub)

    # A clear message instead of an internal server error
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert b"administrators have been notified" in response.content
    pub.refresh_from_db()
    assert not pub.has_container
    # The admins learn which file is missing
    (email,) = mail.outbox
    assert email.to == ["admin@example.com"]
    assert "Missing file in storage" in email.subject


@pytest.mark.django_db
def test_failed_container_is_not_rebuilt_on_every_visit(
    client, pub_with_lost_datafile, monkeypatch
):
    pub = pub_with_lost_datafile
    assert _download(client, pub).status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def must_not_rebuild(self):
        raise AssertionError("the container was rebuilt")

    monkeypatch.setattr(type(pub), "renew_container", must_not_rebuild)
    for _ in range(3):
        assert _download(client, pub).status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert len(mail.outbox) == 1


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
