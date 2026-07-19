import pytest
from django.urls import reverse
from lxml import etree
from topobank_publication.models import Publication
from topobank.testing.factories import SurfaceFactory, Topography1DFactory, UserFactory
from django.utils import timezone
from datetime import timedelta


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def example_authors():
    return [
        {
            "first_name": "Harry",
            "last_name": "Potter",
            "orcid_id": "0000-0000-0000-0000",
            "affiliations": [{"name": "Hogwarts"}],
        }
    ]


@pytest.fixture
def publication(example_authors):
    bob = UserFactory(name="Bob")
    surface = SurfaceFactory(created_by=bob, name="Diamond Structure")
    Topography1DFactory(surface=surface)
    pub = Publication.publish(surface, "cc0-1.0", surface.created_by, example_authors)
    pub.datetime = timezone.now() - timedelta(days=1)
    pub.save()
    return pub


@pytest.mark.django_db
def test_oaipmh_identify(api_client):
    response = api_client.get(reverse('publication:oai-pmh'), {'verb': 'Identify'})
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    namespaces = {'oai': 'http://www.openarchives.org/OAI/2.0/'}
    assert root.tag == '{http://www.openarchives.org/OAI/2.0/}OAI-PMH'
    identify = root.find('oai:Identify', namespaces)
    assert identify is not None
    assert identify.find('oai:repositoryName', namespaces).text == 'contact.engineering publications'
    assert identify.find('oai:protocolVersion', namespaces).text == '2.0'


@pytest.mark.django_db
def test_oaipmh_list_metadata_formats(api_client):
    response = api_client.get(reverse('publication:oai-pmh'), {'verb': 'ListMetadataFormats'})
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    namespaces = {'oai': 'http://www.openarchives.org/OAI/2.0/'}
    formats = root.find('oai:ListMetadataFormats', namespaces)
    assert formats is not None
    prefix = formats.find('oai:metadataFormat/oai:metadataPrefix', namespaces).text
    assert prefix == 'oai_dc'


@pytest.mark.django_db
def test_oaipmh_list_identifiers(api_client, publication):
    response = api_client.get(reverse('publication:oai-pmh'), {'verb': 'ListIdentifiers', 'metadataPrefix': 'oai_dc'})
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    namespaces = {'oai': 'http://www.openarchives.org/OAI/2.0/'}
    list_identifiers = root.find('oai:ListIdentifiers', namespaces)
    assert list_identifiers is not None
    header = list_identifiers.find('oai:header', namespaces)
    identifier = header.find('oai:identifier', namespaces).text
    assert identifier == f'oai:contact.engineering:{publication.short_url}'


@pytest.mark.django_db
def test_oaipmh_list_records(api_client, publication):
    response = api_client.get(reverse('publication:oai-pmh'), {'verb': 'ListRecords', 'metadataPrefix': 'oai_dc'})
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    namespaces = {
        'oai': 'http://www.openarchives.org/OAI/2.0/',
        'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
        'dc': 'http://purl.org/dc/elements/1.1/'
    }
    list_records = root.find('oai:ListRecords', namespaces)
    assert list_records is not None
    record = list_records.find('oai:record', namespaces)
    metadata = record.find('oai:metadata/oai_dc:dc', namespaces)
    title = metadata.find('dc:title', namespaces).text
    assert title == 'Diamond Structure'
    creator = metadata.find('dc:creator', namespaces).text
    assert creator == 'Harry Potter'


@pytest.mark.django_db
def test_oaipmh_get_record(api_client, publication):
    response = api_client.get(reverse('publication:oai-pmh'), {
        'verb': 'GetRecord',
        'identifier': f'oai:contact.engineering:{publication.short_url}',
        'metadataPrefix': 'oai_dc'
    })
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    namespaces = {
        'oai': 'http://www.openarchives.org/OAI/2.0/',
        'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
        'dc': 'http://purl.org/dc/elements/1.1/'
    }
    get_record = root.find('oai:GetRecord', namespaces)
    assert get_record is not None
    record = get_record.find('oai:record', namespaces)
    metadata = record.find('oai:metadata/oai_dc:dc', namespaces)
    title = metadata.find('dc:title', namespaces).text
    assert title == 'Diamond Structure'


@pytest.mark.django_db
def test_oaipmh_error_bad_verb(api_client):
    response = api_client.get(reverse('publication:oai-pmh'), {'verb': 'InvalidVerb'})
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    namespaces = {'oai': 'http://www.openarchives.org/OAI/2.0/'}
    error = root.find('oai:error', namespaces)
    assert error is not None
    assert error.get('code') == 'badVerb'
