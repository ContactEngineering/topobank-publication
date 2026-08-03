"""Tests for the signposting typed links of published datasets.

Signposting lets a client find the identifier, the metadata, the data and the
license of a dataset from the landing page alone, without parsing any HTML, see
https://signposting.org/FAIR/ and
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import re

import pytest
from django.urls import reverse

from topobank_publication.models import Publication
from topobank_publication.signposting import signposting_links


def _parse(header):
    """Return (relation, target, attributes) triples of a `Link` header."""
    links = []
    for value in re.findall(r"<[^>]+>[^,]*", header):
        target = re.match(r"<([^>]+)>", value).group(1)
        attributes = dict(re.findall(r'(\w+)="([^"]*)"', value))
        links.append((attributes.pop("rel"), target, attributes))
    return links


def _targets(header, relation):
    return [target for rel, target, _ in _parse(header) if rel == relation]


@pytest.fixture
def minted_pub(example_pub):
    """A publication with a DOI, as every published dataset ends up having."""
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.doi_state = Publication.DOI_STATE_FINDABLE
    example_pub.save()
    return example_pub


@pytest.mark.django_db
def test_doi_is_advertised_as_the_identifier_to_cite(rf, minted_pub):
    header = ", ".join(signposting_links(minted_pub, rf.get("/go/abcde/")))

    assert _targets(header, "cite-as") == ["https://doi.org/10.12345/ce-abcde"]


@pytest.mark.django_db
def test_short_url_is_not_advertised_as_persistent(rf, example_pub):
    """Only a DOI qualifies; the short URL is not a persistent identifier."""
    header = ", ".join(signposting_links(example_pub, rf.get("/go/abcde/")))

    assert _targets(header, "cite-as") == []


@pytest.mark.django_db
def test_metadata_and_data_are_linked_with_their_media_types(rf, minted_pub):
    links = _parse(", ".join(signposting_links(minted_pub, rf.get("/go/abcde/"))))
    by_relation = {rel: (target, attributes) for rel, target, attributes in links}

    described_by, described_by_attrs = by_relation["describedby"]
    assert described_by.endswith(
        reverse("publication:metadata", kwargs={"short_url": minted_pub.short_url})
    )
    assert described_by_attrs["type"] == "application/ld+json"

    item, item_attrs = by_relation["item"]
    assert item.endswith(
        reverse(
            "publication:download-container",
            kwargs={"short_url": minted_pub.short_url},
        )
    )
    assert item_attrs["type"] == "application/zip"


@pytest.mark.django_db
def test_license_is_linked(rf, minted_pub):
    header = ", ".join(signposting_links(minted_pub, rf.get("/go/abcde/")))

    assert _targets(header, "license") == [
        "https://creativecommons.org/publicdomain/zero/1.0/legalcode"
    ]


@pytest.mark.django_db
def test_authors_with_an_orcid_are_linked(rf, minted_pub):
    header = ", ".join(signposting_links(minted_pub, rf.get("/go/abcde/")))

    authors = _targets(header, "author")
    assert all(target.startswith("https://orcid.org/") for target in authors)
    assert len(authors) == len(
        [a for a in minted_pub.authors_json if a.get("orcid_id")]
    )


@pytest.mark.django_db
def test_authors_without_an_orcid_are_not_linked(rf, minted_pub):
    minted_pub.authors_json = [
        {
            "first_name": "Anonymous",
            "last_name": "Author",
            "orcid_id": "",
            "affiliations": [],
        }
    ]

    header = ", ".join(signposting_links(minted_pub, rf.get("/go/abcde/")))

    assert _targets(header, "author") == []


@pytest.mark.django_db
def test_resource_types_are_advertised(rf, minted_pub):
    header = ", ".join(signposting_links(minted_pub, rf.get("/go/abcde/")))

    assert set(_targets(header, "type")) == {
        "https://schema.org/AboutPage",
        "https://schema.org/Dataset",
    }


@pytest.mark.django_db
def test_go_redirect_carries_the_links(client, minted_pub):
    response = client.get(
        minted_pub.get_absolute_url(),
        headers={"accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
    )

    assert response.status_code == 302
    assert _targets(response["Link"], "cite-as") == [
        "https://doi.org/10.12345/ce-abcde"
    ]


@pytest.mark.django_db
def test_metadata_endpoint_carries_the_links(client, minted_pub):
    response = client.get(
        reverse("publication:metadata", kwargs={"short_url": minted_pub.short_url})
    )

    assert response.status_code == 200
    assert _targets(response["Link"], "describedby")


@pytest.mark.django_db
def test_download_carries_the_links(client, minted_pub):
    response = client.get(
        reverse(
            "publication:download-container",
            kwargs={"short_url": minted_pub.short_url},
        )
    )

    assert response.status_code == 200
    assert _targets(response["Link"], "item")
