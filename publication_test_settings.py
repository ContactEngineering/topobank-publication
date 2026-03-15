import environ

from test_settings import *  # noqa: F403

env = environ.Env()

INSTALLED_APPS = INSTALLED_APPS + [  # noqa: F405
    "topobank_publication.apps.PublicationAppConfig",
]

ROOT_URLCONF = "publication_test_urls"

MIDDLEWARE += ["topobank.middleware.anonymous_user_middleware"]  # noqa: F405

DATACITE_USERNAME = env("DATACITE_USERNAME", default="test")
DATACITE_PASSWORD = env("DATACITE_PASSWORD", default="test")
DATACITE_API_URL = env("DATACITE_API_URL", default="https://api.test.datacite.org")
PUBLICATION_DOI_PREFIX = env("PUBLICATION_DOI_PREFIX", default="10.12345")
