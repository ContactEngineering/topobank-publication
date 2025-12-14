import pytest
from django.urls import reverse
from topobank.testing.factories import SurfaceFactory, UserFactory

from topobank_publication.models import Publication


@pytest.mark.django_db
def test_sharing_status_filter(api_client, example_authors, handle_usage_statistics):
    lancelot = UserFactory(name="lancelot")
    parceval = UserFactory(name="parceval")

    SurfaceFactory(name="own-hidden", created_by=lancelot)

    surface_shared_egress = SurfaceFactory(name="shared-egress", created_by=lancelot)
    surface_shared_egress.grant_permission(parceval)

    surface_published_egress = SurfaceFactory(name="published-egress", created_by=lancelot)
    Publication.publish(surface_published_egress, "cc0-1.0", surface_published_egress.created_by, example_authors)
    # NOTE THAT THIS CREATES A COPY !!!!

    surface_shared_ingress = SurfaceFactory(name="shared-ingress", created_by=parceval)
    surface_shared_ingress.grant_permission(lancelot)
    surface_published_ingress = SurfaceFactory(
        name="published-ingress", created_by=parceval
    )
    Publication.publish(surface_published_ingress, "cc0-1.0", surface_published_ingress.created_by, example_authors)
    SurfaceFactory(name="invisible", created_by=parceval)

    api_client.force_login(lancelot)

    result = api_client.get(reverse("manager:surface-api-list") + "?sharing_status=all").data
    assert len(result) == 6  # All

    result = api_client.get(reverse("manager:surface-api-list") + "?sharing_status=own").data
    assert len(result) == 3  # Lancelot's, without published

    result = api_client.get(reverse("manager:surface-api-list") + "?sharing_status=others").data
    assert len(result) == 1  # Others, without published
    assert result[0]["name"] == "shared-ingress"

    result = api_client.get(reverse("manager:surface-api-list") + "?sharing_status=published").data
    assert len(result) == 2  # All published
    assert sorted([r["name"] for r in result]) == [
        "published-egress",
        "published-ingress",
    ]
