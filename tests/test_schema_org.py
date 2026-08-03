"""Tests for the schema.org description of a published dataset.

The DataCite record is only reachable through DataCite. This is the same
description served by the application itself, in the vocabulary generic
harvesters understand, see
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import json

import pytest
from django.urls import reverse
from topobank.testing.factories import (SurfaceFactory, Topography1DFactory,
                                        UserFactory)

from topobank_publication.models import Publication, PublicationCollection
from topobank_publication.schema_org import schema_org_dataset
from topobank_publication.views import JSONLD_CONTENT_TYPE


@pytest.fixture
def described(rf, example_pub):
    """The schema.org description of the example publication."""
    return schema_org_dataset(example_pub, rf.get("/go/abcde/"))


@pytest.mark.django_db
def test_document_is_a_dataset(described):
    assert described["@context"] == "https://schema.org"
    assert described["@type"] == "Dataset"


@pytest.mark.django_db
def test_descriptive_metadata_is_included(described, example_pub):
    assert described["name"] == example_pub.surface.name
    assert described["description"] == example_pub.surface.description
    assert described["version"] == str(example_pub.version)
    assert described["datePublished"] == example_pub.datetime.isoformat()
    assert described["inLanguage"] == "en"


@pytest.mark.django_db
def test_data_download_is_included(described, example_pub):
    """Without this, the document describes the landing page only."""
    distribution = described["distribution"]

    assert len(distribution) == 1
    assert distribution[0]["@type"] == "DataDownload"
    assert distribution[0]["encodingFormat"] == "application/zip"
    assert distribution[0]["contentUrl"].endswith(
        reverse(
            "publication:download-container",
            kwargs={"short_url": example_pub.short_url},
        )
    )


@pytest.mark.django_db
def test_license_and_access_conditions_are_separate(described):
    assert described["license"] == (
        "https://creativecommons.org/publicdomain/zero/1.0/legalcode"
    )
    assert described["isAccessibleForFree"] is True
    assert described["conditionsOfAccess"] == "open access"


@pytest.mark.django_db
def test_authors_are_creators_with_orcid_and_affiliation(described):
    creators = described["creator"]

    assert [creator["name"] for creator in creators] == [
        "Hermione Granger",
        "Harry Potter",
    ]
    assert creators[0]["@id"].startswith("https://orcid.org/")
    assert creators[0]["affiliation"][0]["@type"] == "Organization"


@pytest.mark.django_db
def test_repository_is_named_as_catalog_and_publisher(described):
    assert described["includedInDataCatalog"]["@type"] == "DataCatalog"
    assert described["includedInDataCatalog"]["name"] == "contact.engineering"
    assert described["publisher"]["name"] == "contact.engineering"


@pytest.mark.django_db
def test_keywords_include_tags(rf, db, example_authors):
    user = UserFactory()
    surface = SurfaceFactory(created_by=user, name="Tagged dataset")
    Topography1DFactory(surface=surface)
    surface.tags = ["diamond", "polished"]
    surface.save()

    publication = Publication.publish(surface, "cc0-1.0", user, example_authors)
    described = schema_org_dataset(publication, rf.get("/go/abcde/"))

    assert set(described["keywords"]) >= {"surface", "topography", "diamond", "polished"}


@pytest.mark.django_db
def test_landing_page_identifies_the_dataset_without_a_doi(described, example_pub):
    """DOI creation can still be pending, and then there is nothing else."""
    assert not example_pub.has_doi
    assert described["@id"] == described["url"]
    assert described["identifier"] == described["url"]
    assert "sameAs" not in described


@pytest.mark.django_db
def test_doi_identifies_the_dataset_when_present(rf, example_pub):
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.doi_state = Publication.DOI_STATE_FINDABLE
    example_pub.save()

    described = schema_org_dataset(example_pub, rf.get("/go/abcde/"))

    assert described["@id"] == "https://doi.org/10.12345/ce-abcde"
    assert described["identifier"] == "https://doi.org/10.12345/ce-abcde"
    assert described["sameAs"] == "https://doi.org/10.12345/ce-abcde"
    assert described["url"].endswith(example_pub.get_absolute_url())


@pytest.mark.django_db
def test_collection_membership_is_included(rf, example_pub):
    collection = PublicationCollection.objects.create(
        title="A collection",
        publisher=example_pub.publisher,
        unique_hash="test-hash",
        doi_name="10.12345/ce-coll-1",
        doi_state=Publication.DOI_STATE_FINDABLE,
    )
    collection.publications.set([example_pub])

    described = schema_org_dataset(example_pub, rf.get("/go/abcde/"))

    assert described["isPartOf"] == [
        {
            "@type": "Collection",
            "@id": "https://doi.org/10.12345/ce-coll-1",
            "name": "A collection",
        }
    ]


@pytest.mark.django_db
def test_collection_without_doi_is_not_referenced(rf, example_pub):
    collection = PublicationCollection.objects.create(
        title="A collection", publisher=example_pub.publisher, unique_hash="test-hash"
    )
    collection.publications.set([example_pub])

    assert "isPartOf" not in schema_org_dataset(example_pub, rf.get("/go/abcde/"))


@pytest.mark.django_db
def test_metadata_endpoint_serves_json_ld(client, example_pub):
    response = client.get(
        reverse("publication:metadata", kwargs={"short_url": example_pub.short_url})
    )

    assert response.status_code == 200
    assert response["Content-Type"] == JSONLD_CONTENT_TYPE
    assert json.loads(response.content)["name"] == example_pub.surface.name


@pytest.mark.django_db
def test_metadata_endpoint_404s_for_unknown_dataset(client):
    response = client.get(
        reverse("publication:metadata", kwargs={"short_url": "nosuch"})
    )

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "accept", ["application/ld+json", "application/vnd.schemaorg.ld+json"]
)
def test_go_serves_json_ld_on_content_negotiation(client, example_pub, accept):
    response = client.get(example_pub.get_absolute_url(), headers={"accept": accept})

    assert response.status_code == 200
    assert response["Content-Type"] == JSONLD_CONTENT_TYPE
    assert json.loads(response.content)["@type"] == "Dataset"


@pytest.mark.django_db
def test_go_still_redirects_browsers_to_the_app(client, example_pub):
    response = client.get(
        example_pub.get_absolute_url(),
        headers={"accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
    )

    assert response.status_code == 302
    assert response["Location"] == f"/ui/dataset-detail/{example_pub.surface.pk}/"


@pytest.mark.django_db
def test_go_still_redirects_json_clients_to_the_api(client, example_pub):
    response = client.get(
        example_pub.get_absolute_url(), headers={"accept": "application/json"}
    )

    assert response.status_code == 302
    assert response["Location"] == example_pub.get_api_url()
