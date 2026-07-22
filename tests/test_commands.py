"""
Test management commands for publication app.
"""

import pytest
from django.core.management import call_command

from topobank_publication.testing.factories import PublicationFactory


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
    # Corrected policy (see renew_containers docstring / command):
    #  - has DOI *and* a container -> skipped (immutable, must not change)
    #  - has DOI but missing container -> container IS (re)created
    #  - no DOI -> renewed regardless
    pub_doi_with_container = PublicationFactory(doi_name='10.4545/abcde')  # skipped
    pub_doi_no_container = PublicationFactory(doi_name='10.4545/xyz')  # renewed
    pub_no_doi = PublicationFactory()  # renewed
    assert pub_doi_no_container.pk != pub_doi_with_container.pk
    assert pub_no_doi.pk != pub_doi_with_container.pk

    settings.PUBLICATION_DOI_MANDATORY = True

    # Only the first publication actually has a container in storage. The
    # factory does not create real container files, so we control has_container
    # per-instance via a property whose getter inspects the pk.
    with_container_pks = {pub_doi_with_container.pk}

    def fake_has_container(self):
        return self.pk in with_container_pks

    mocker.patch(
        'topobank_publication.models.Publication.has_container',
        property(fake_has_container),
    )
    m = mocker.patch('topobank_publication.models.Publication.renew_container')

    call_command('renew_containers')

    m.assert_called()
    # DOI+container is skipped; DOI-without-container and no-DOI are both renewed.
    assert m.call_count == 2
