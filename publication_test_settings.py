from test_settings import *

INSTALLED_APPS = INSTALLED_APPS + [
    "topobank_publication.apps.PublicationAppConfig",
]

ROOT_URLCONF = "publication_test_urls"

DATACITE_USERNAME = "test"
DATACITE_PASSWORD = "test"
DATACITE_API_URL = "https://api.test.datacite.org"
PUBLICATION_DOI_PREFIX = "10.12345"
