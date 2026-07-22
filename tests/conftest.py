import datetime
import logging
import random

import pytest
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from freezegun import freeze_time
from topobank.testing.factories import (OrganizationFactory, SurfaceFactory,
                                        UserFactory)
from topobank.testing.fixtures import api_client  # noqa: F401
from topobank.testing.fixtures import example_authors  # noqa: F401
from topobank.testing.fixtures import handle_usage_statistics  # noqa: F401
from topobank.testing.fixtures import one_line_scan  # noqa: F401
from topobank.testing.fixtures import test_workflow  # noqa: F401
from topobank.testing.fixtures import two_users  # noqa: F401

from topobank_publication.models import Publication

_log = logging.getLogger(__name__)


# =============================================================================
# Short URL Offset Configuration
# =============================================================================
# The DOI name of a publication is derived from its short_url, which encodes
# ``publication.id + SHORT_URL_OFFSET`` (see topobank_publication/signals.py).
# CI uses a fresh database every run, so ids restart at 1; with a *constant*
# offset every run would produce the *same* DOI names and collide with draft
# DOIs left over from previous runs (or created by a concurrent run) on the
# shared DataCite test account ("This DOI has already been taken").
#
# Pick a random per-session offset so each test run (and each concurrent CI
# job) uses a disjoint DOI namespace. SystemRandom draws from OS entropy, so
# two processes starting at the same instant still get independent offsets.
# The range keeps the encoded short_url comfortably within its 10-char column.
SHORT_URL_OFFSET = random.SystemRandom().randint(10**6, 10**9)
settings.SHORT_URL_OFFSET = SHORT_URL_OFFSET


@pytest.fixture(autouse=True)
def _enable_db_access_for_all_tests(db):
    """Restore the implicit DB access previously provided by the removed
    autouse `sync_workflows` fixture in topobank.testing.fixtures."""


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


# Placeholder credential values that mean "not really configured". The test
# settings default DATACITE_USERNAME/PASSWORD to "test" when the secrets are
# absent (e.g. on fork PRs, which never receive repository secrets).
_DATACITE_PLACEHOLDER_CREDENTIALS = {"", "test"}


def is_datacite_configured():
    """Check if DataCite credentials are properly configured for testing.

    Returns True only if:
    - DATACITE_API_URL points at the test API ('api.test.datacite.org'),
    - PUBLICATION_DOI_PREFIX is a real prefix (starts with '10.'), and
    - DATACITE_USERNAME/PASSWORD are set to real, non-placeholder values.

    The credential check matters because the settings default the username and
    password to the placeholder "test" when the secrets are missing. Without
    it, secret-less runs (notably fork PRs) would *run* the integration tests
    with junk credentials and fail with a 404 instead of skipping cleanly.
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

    # Check that real credentials are configured (not missing / the "test"
    # placeholder default from the settings module).
    username = getattr(settings, "DATACITE_USERNAME", "")
    password = getattr(settings, "DATACITE_PASSWORD", "")
    if (username in _DATACITE_PLACEHOLDER_CREDENTIALS
            or password in _DATACITE_PLACEHOLDER_CREDENTIALS):
        _log.warning("DataCite skip: username/password missing or set to the "
                     "placeholder default")
        return False

    return True


def get_datacite_skip_reason():
    """Return a descriptive skip reason showing actual configuration values."""
    from django.conf import settings

    doi_prefix = getattr(settings, "PUBLICATION_DOI_PREFIX", "99.999")
    api_url = getattr(settings, "DATACITE_API_URL", "")
    username = getattr(settings, "DATACITE_USERNAME", "")
    has_credentials = (
        username not in _DATACITE_PLACEHOLDER_CREDENTIALS
        and getattr(settings, "DATACITE_PASSWORD", "")
        not in _DATACITE_PLACEHOLDER_CREDENTIALS
    )
    return (
        f"DataCite not configured: DOI_PREFIX='{doi_prefix}', "
        f"API_URL='{api_url}', credentials_configured={has_credentials}"
    )


# Skip marker for DataCite integration tests
datacite_not_configured = pytest.mark.skipif(
    not is_datacite_configured(),
    reason=get_datacite_skip_reason(),
)


# Only draft DOIs whose name matches the publication test pattern are swept.
# Publication DOIs are minted as "<prefix>/ce-<short_url>", so "/ce-" marks a
# DOI created by this test suite and distinguishes it from anything else that
# might exist under the prefix.
_DATACITE_TEST_DOI_MARKER = "/ce-"


def _list_draft_dois_under_prefix():
    """Return the names of all draft DOIs under PUBLICATION_DOI_PREFIX.

    Best-effort: on any error (listing unsupported, network issue) returns an
    empty list so cleanup degrades gracefully.
    """
    import requests
    from django.conf import settings

    api_url = settings.DATACITE_API_URL.rstrip("/")
    auth = (settings.DATACITE_USERNAME, settings.DATACITE_PASSWORD)
    draft_dois = []
    url = f"{api_url}/dois"
    params = {
        "prefix": settings.PUBLICATION_DOI_PREFIX,
        "state": "draft",
        "page[size]": 100,
    }
    # Follow pagination via links.next, with a hard page cap as a safety net.
    for _ in range(50):
        try:
            response = requests.get(url, params=params, auth=auth, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            _log.warning(f"Could not list draft DOIs for cleanup: {exc}")
            break
        for entry in payload.get("data", []):
            attributes = entry.get("attributes", {})
            doi = attributes.get("doi") or entry.get("id")
            if doi and attributes.get("state") == "draft":
                draft_dois.append(doi)
        next_url = payload.get("links", {}).get("next")
        if not next_url:
            break
        # Subsequent pages: the "next" link already carries the query string.
        url, params = next_url, None
    return draft_dois


@pytest.fixture(scope="session")
def datacite_cleanup_registry():
    """
    Session-scoped fixture that collects DOIs created during tests
    and deletes them at the end of the test session.

    Cleanup runs in two passes so that draft DOIs are removed even when a test
    fails before registering its DOI, and so that leftovers from a previous
    crashed run do not accumulate (and later cause "DOI already taken"):

    1. Delete every DOI explicitly registered by a test.
    2. Sweep the DataCite test account for any remaining draft DOIs under the
       publication test prefix and delete those too.

    The sweep is safe because the CI workflow serializes runs (see the
    ``concurrency`` group in .github/workflows/test.yml), so no other run's
    in-flight drafts are present during teardown.
    """
    created_dois = []
    yield created_dois

    if not is_datacite_configured():
        _log.warning("Cannot cleanup DOIs - DataCite not configured")
        return

    from datacite import DataCiteRESTClient
    from datacite.errors import DataCiteError, HttpError
    from django.conf import settings

    client = DataCiteRESTClient(
        username=settings.DATACITE_USERNAME,
        password=settings.DATACITE_PASSWORD,
        prefix=settings.PUBLICATION_DOI_PREFIX,
        url=settings.DATACITE_API_URL,
    )

    def _delete(doi):
        try:
            _log.info(f"Deleting draft DOI: {doi}")
            client.delete_doi(doi)
            _log.info(f"Successfully deleted DOI: {doi}")
        except (DataCiteError, HttpError) as exc:
            _log.warning(f"Failed to delete DOI {doi}: {exc}")

    # Pass 1: explicitly registered DOIs.
    deleted = set()
    _log.info(f"Cleaning up {len(created_dois)} registered draft DOIs...")
    for doi in created_dois:
        if doi and doi not in deleted:
            _delete(doi)
            deleted.add(doi)

    # Pass 2: sweep any remaining draft DOIs created by this suite (leftovers
    # from failed tests or earlier crashed runs).
    for doi in _list_draft_dois_under_prefix():
        if doi in deleted or _DATACITE_TEST_DOI_MARKER not in doi:
            continue
        _delete(doi)
        deleted.add(doi)
