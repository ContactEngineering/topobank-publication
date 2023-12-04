import datetime

import pytest
from freezegun import freeze_time

from ..models import Publication

from topobank.manager.tests.utils import SurfaceFactory
from topobank.users.tests.factories import UserFactory


@pytest.mark.django_db
@pytest.fixture
def example_pub(example_authors):
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
