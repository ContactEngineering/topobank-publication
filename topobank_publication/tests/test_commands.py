"""
Test management commands for publication app.
"""

from django.core.management import call_command

import pytest

from .utils import PublicationFactory


@pytest.mark.django_db
def test_complete_dois(mocker, settings):
    PublicationFactory(doi_name='10.4545/abcde')
    PublicationFactory()
    PublicationFactory()

    settings.PUBLICATION_DOI_MANDATORY = True
    m = mocker.patch('topobank_publication.models.Publication.create_doi')

    call_command('complete_dois', do_it=True, force_draft=True)

    m.assert_called()
    assert m.call_count == 2


@pytest.mark.django_db
def test_renew_containers(mocker, settings):
    PublicationFactory(doi_name='10.4545/abcde')  # should not get a new container
    PublicationFactory(doi_name='10.4545/xyz')  # should not get a new container
    PublicationFactory()  # only this one should get a new container

    settings.PUBLICATION_DOI_MANDATORY = True
    m = mocker.patch('topobank_publication.models.Publication.renew_container')

    call_command('renew_containers')

    m.assert_called()
    assert m.call_count == 1
