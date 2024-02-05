import datetime

import pytest
from ce_ui.tests.fixtures import orcid_socialapp  # noqa: F401
from freezegun import freeze_time
from topobank.fixtures import example_authors  # noqa: F401
from topobank.fixtures import handle_usage_statistics  # noqa: F401
from topobank.fixtures import sync_analysis_functions  # noqa: F401
from topobank.fixtures import test_analysis_function  # noqa: F401
from topobank.manager.tests.utils import SurfaceFactory  # noqa: F401
from topobank.manager.tests.utils import one_line_scan, two_users  # noqa: F401
from topobank.organizations.tests.utils import OrganizationFactory
from topobank.users.tests.factories import UserFactory

from ..models import Publication


@pytest.mark.django_db
@pytest.fixture
def example_pub(example_authors):  # noqa: F811
    """Fixture returning a publication which can be used as test example"""

    user = UserFactory()

    publication_date = datetime.date(2020, 1, 1)
    description = "This is a nice surface for testing."
    name = "Diamond Structure"

    surface = SurfaceFactory(name=name, creator=user, description=description)
    surface.tags = ['diamond']

    with freeze_time(publication_date):
        pub = Publication.publish(surface, 'cc0-1.0', example_authors)

    return pub


@pytest.mark.django_db
@pytest.fixture
def user_with_plugin():
    org_name = "Test Organization"
    org = OrganizationFactory(name=org_name, plugins_available="topobank_publication")
    user = UserFactory()
    user.groups.add(org.group)
    return user
