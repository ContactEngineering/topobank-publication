import datetime
import logging

import pytest
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from freezegun import freeze_time
from topobank.testing.factories import (OrganizationFactory, SurfaceFactory,
                                        UserFactory)
from topobank.testing.fixtures import example_authors  # noqa: F401
from topobank.testing.fixtures import handle_usage_statistics  # noqa: F401
from topobank.testing.fixtures import one_line_scan  # noqa: F401
from topobank.testing.fixtures import sync_analysis_functions  # noqa: F401
from topobank.testing.fixtures import test_analysis_function  # noqa: F401
from topobank.testing.fixtures import two_users  # noqa: F401

from topobank_publication.models import Publication

_log = logging.getLogger(__name__)


# =============================================================================
# Short URL Offset Configuration
# =============================================================================
# Set SHORT_URL_OFFSET to avoid conflicts with existing DOIs in DataCite test
# system. This shifts the ID used for short_url encoding.
settings.SHORT_URL_OFFSET = 1000000


@pytest.fixture
def example_pub(db, example_authors):  # noqa: F811
    """Fixture returning a publication which can be used as test example."""
    user = UserFactory()

    publication_date = datetime.date(2020, 1, 1)
    description = "This is a nice surface for testing."
    name = "Diamond Structure"

    surface = SurfaceFactory(name=name, created_by=user, description=description)
    surface.tags = ["diamond"]

    with freeze_time(publication_date):
        pub = Publication.publish(surface, "cc0-1.0", surface.created_by, example_authors)

    return pub


@pytest.fixture
def user_with_plugin(db):
    """Fixture returning a user with publication plugin access."""
    org_name = "Test Organization"
    org = OrganizationFactory(name=org_name, plugins_available="topobank_publication")
    user = UserFactory()
    user.groups.add(org.group)
    return user


@pytest.fixture
def orcid_socialapp(db):
    """Fixture for ORCID social app."""
    social_app = SocialApp.objects.create(provider="orcid", name="ORCID")
    social_app.sites.set([1])
    return social_app


# =============================================================================
# DataCite Integration Test Fixtures
# =============================================================================


def is_datacite_configured():
    """Check if DataCite credentials are properly configured for testing.

    Returns True if:
    - DATACITE_API_URL contains 'api.test.datacite.org' (test API, not production)
    - PUBLICATION_DOI_PREFIX starts with '10.' (valid DOI prefix format)
    """
    from django.conf import settings

    # Check that we're using the test API, not production
    api_url = getattr(settings, "DATACITE_API_URL", "")
    if "api.test.datacite.org" not in api_url:
        _log.warning(f"DataCite skip: API URL '{api_url}' does not contain 'api.test.datacite.org'")
        return False

    # Check that we have a valid DOI prefix (must start with "10.")
    doi_prefix = getattr(settings, "PUBLICATION_DOI_PREFIX", "99.999")
    if not doi_prefix.startswith("10."):
        _log.warning(f"DataCite skip: DOI prefix '{doi_prefix}' does not start with '10.'")
        return False

    return True


def get_datacite_skip_reason():
    """Return a descriptive skip reason showing actual configuration values."""
    from django.conf import settings

    doi_prefix = getattr(settings, "PUBLICATION_DOI_PREFIX", "99.999")
    api_url = getattr(settings, "DATACITE_API_URL", "")
    return f"DataCite not configured: DOI_PREFIX='{doi_prefix}', API_URL='{api_url}'"


# Skip marker for DataCite integration tests
datacite_not_configured = pytest.mark.skipif(
    not is_datacite_configured(),
    reason=get_datacite_skip_reason(),
)


@pytest.fixture(scope="session")
def datacite_cleanup_registry():
    """
    Session-scoped fixture that collects DOIs created during tests
    and deletes them at the end of the test session.

    This ensures all draft DOIs created during testing are cleaned up,
    even if individual tests fail.
    """
    created_dois = []
    yield created_dois

    # Cleanup at end of session
    if not created_dois:
        _log.info("No DOIs to clean up")
        return

    if not is_datacite_configured():
        _log.warning("Cannot cleanup DOIs - DataCite not configured")
        return

    from datacite import DataCiteRESTClient
    from datacite.errors import DataCiteError, HttpError
    from django.conf import settings

    _log.info(f"Cleaning up {len(created_dois)} draft DOIs created during tests...")
    client = DataCiteRESTClient(
        username=settings.DATACITE_USERNAME,
        password=settings.DATACITE_PASSWORD,
        prefix=settings.PUBLICATION_DOI_PREFIX,
        url=settings.DATACITE_API_URL,
    )

    for doi in created_dois:
        try:
            _log.info(f"Deleting draft DOI: {doi}")
            client.delete_doi(doi)
            _log.info(f"Successfully deleted DOI: {doi}")
        except (DataCiteError, HttpError) as exc:
            _log.warning(f"Failed to delete DOI {doi}: {exc}")
