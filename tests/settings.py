'''Django settings for MaRDMO's tests: RDMO's defaults with MaRDMO installed.

The MaRDI Portal URLs are the real ones, so the tests read the same
items.json and properties.json as production; network requests are
blocked by pytest-socket (see pyproject.toml), the tests use recorded
answers instead.  The OAuth2 credentials are dummies.
'''
from pathlib import Path

from rdmo.core.settings import *  # noqa: F401,F403  (RDMO's defaults)
from rdmo.core.settings import INSTALLED_APPS, PROJECT_EXPORTS, _

BASE_DIR = Path(__file__).parent
MEDIA_ROOT = BASE_DIR / 'media_root'
STATIC_ROOT = BASE_DIR / 'static_root'

SECRET_KEY = 'mardmo-tests'
DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

INSTALLED_APPS = ['MaRDMO'] + INSTALLED_APPS

ROOT_URLCONF = 'tests.urls'

MARDMO_PROVIDER = {
    'mardi': {
        'items': 'data/items.json',
        'properties': 'data/properties.json',
        'api': 'https://portal.mardi4nfdi.de/w/api.php',
        'sparql': 'https://query.portal.mardi4nfdi.de/sparql',
        'uri': 'https://portal.mardi4nfdi.de',
        'entity_uri': 'http://portal.mardi4nfdi.de',
        'oauth2_client_id': 'mardmo-tests',
        'oauth2_client_secret': 'mardmo-tests',
    },
}

# As in the README
from MaRDMO.optionsets import OPTIONSET_PROVIDERS as MARDMO_OPTIONSET_PROVIDERS  # noqa: E402
OPTIONSET_PROVIDERS = MARDMO_OPTIONSET_PROVIDERS

PROJECT_EXPORTS = PROJECT_EXPORTS + [
    ('wikibase', _('Export to MaRDI Portal'), 'MaRDMO.main.MaRDMOExportProvider'),
    ('wikibase-search', _('Query MaRDI Portal'), 'MaRDMO.main.MaRDMOQueryProvider'),
]
