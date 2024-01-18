import datetime

import pytest
from freezegun import freeze_time

from ..models import Publication

from topobank.fixtures import example_authors, handle_usage_statistics, sync_analysis_functions, \
    test_analysis_function  # noqa: F401
from topobank.manager.tests.utils import one_line_scan, two_users, SurfaceFactory  # noqa: F401
from topobank.users.tests.factories import UserFactory
from topobank.organizations.tests.utils import OrganizationFactory


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
