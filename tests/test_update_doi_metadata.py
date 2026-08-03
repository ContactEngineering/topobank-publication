"""Tests for refreshing the DataCite metadata of already minted DOIs.

Improvements to the generated metadata otherwise only reach DOIs minted after
the improvement, see
https://github.com/ContactEngineering/topobank-publication/issues/21.
"""

import pytest
from django.core.management import call_command

from topobank_publication.models import Publication
from topobank_publication.testing.factories import PublicationFactory
from topobank_publication.utils import DOICreationException

REST_CLIENT = "topobank_publication.doi_mixin.DataCiteRESTClient"


@pytest.fixture
def rest_client(mocker):
    """Patch the DataCite client and return the mocked instance."""
    return mocker.patch(REST_CLIENT).return_value


@pytest.mark.django_db
def test_metadata_is_pushed_to_datacite(rest_client, example_pub):
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.datacite_json = {"titles": [{"title": "Something stale"}]}
    example_pub.save()

    assert example_pub.update_doi_metadata() is True

    rest_client.update_doi.assert_called_once()
    kwargs = rest_client.update_doi.call_args.kwargs
    assert kwargs["doi"] == "10.12345/ce-abcde"
    assert kwargs["metadata"]["titles"] == [{"title": example_pub.surface.name}]


@pytest.mark.django_db
def test_api_only_attributes_are_pushed_too(rest_client, example_pub):
    """Attributes outside the kernel-4 schema must survive the update.

    They are excluded from schema validation, which must not mean they are
    excluded from what is sent: carrying them to the DOIs that were minted
    before they existed is the point of this command.
    """
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.save()

    example_pub.update_doi_metadata()

    metadata = rest_client.update_doi.call_args.kwargs["metadata"]
    for attribute in example_pub.DATACITE_API_ONLY_ATTRIBUTES:
        assert attribute in metadata
    assert metadata["contentUrl"] == [example_pub.container_url]


@pytest.mark.django_db
def test_regenerated_metadata_is_stored(rest_client, example_pub):
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.datacite_json = {"titles": [{"title": "Something stale"}]}
    example_pub.save()

    example_pub.update_doi_metadata()

    example_pub.refresh_from_db()
    assert example_pub.datacite_json == example_pub.get_datacite_metadata(
        example_pub.doi_name
    )


@pytest.mark.django_db
def test_landing_page_url_is_not_touched(rest_client, example_pub):
    """`get_full_url` returns the DOI URL once minted; it must not be resent.

    Sending it as the target of the DOI would make the DOI resolve to itself.
    """
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.save()

    example_pub.update_doi_metadata()

    assert "url" not in rest_client.update_doi.call_args.kwargs
    rest_client.update_url.assert_not_called()


@pytest.mark.django_db
def test_doi_state_is_not_touched(rest_client, example_pub):
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.doi_state = Publication.DOI_STATE_FINDABLE
    example_pub.save()

    example_pub.update_doi_metadata()

    assert "event" not in rest_client.update_doi.call_args.kwargs["metadata"]
    example_pub.refresh_from_db()
    assert example_pub.doi_state == Publication.DOI_STATE_FINDABLE


@pytest.mark.django_db
def test_unchanged_metadata_does_not_contact_datacite(rest_client, example_pub):
    example_pub.doi_name = "10.12345/ce-abcde"
    example_pub.datacite_json = example_pub.get_datacite_metadata("10.12345/ce-abcde")
    example_pub.save()

    assert example_pub.update_doi_metadata() is False

    rest_client.update_doi.assert_not_called()


@pytest.mark.django_db
def test_object_without_doi_is_rejected(rest_client, example_pub):
    with pytest.raises(DOICreationException):
        example_pub.update_doi_metadata()

    rest_client.update_doi.assert_not_called()


@pytest.mark.django_db
def test_command_updates_only_publications_with_a_doi(mocker):
    PublicationFactory(doi_name="10.12345/ce-abcde")
    PublicationFactory(doi_name="10.12345/ce-fghij")
    PublicationFactory()  # no DOI

    update = mocker.patch(
        "topobank_publication.models.Publication.update_doi_metadata",
        return_value=True,
    )

    call_command("update_doi_metadata", do_it=True)

    assert update.call_count == 2


@pytest.mark.django_db
def test_command_is_a_dry_run_by_default(mocker):
    PublicationFactory(doi_name="10.12345/ce-abcde")

    update = mocker.patch(
        "topobank_publication.models.Publication.update_doi_metadata"
    )

    call_command("update_doi_metadata")

    update.assert_not_called()


@pytest.mark.django_db
def test_command_can_target_a_single_record(mocker):
    target = PublicationFactory(doi_name="10.12345/ce-abcde")
    PublicationFactory(doi_name="10.12345/ce-fghij")

    update = mocker.patch(
        "topobank_publication.models.Publication.update_doi_metadata",
        return_value=True,
    )

    call_command("update_doi_metadata", do_it=True, short_url=target.short_url)

    assert update.call_count == 1


@pytest.mark.django_db
def test_command_continues_after_a_failing_record(mocker):
    PublicationFactory(doi_name="10.12345/ce-abcde")
    PublicationFactory(doi_name="10.12345/ce-fghij")
    PublicationFactory(doi_name="10.12345/ce-klmno")

    update = mocker.patch(
        "topobank_publication.models.Publication.update_doi_metadata",
        side_effect=[DOICreationException("nope"), True, True],
    )

    call_command("update_doi_metadata", do_it=True)

    assert update.call_count == 3
