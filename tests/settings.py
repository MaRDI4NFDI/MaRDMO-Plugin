'''Django settings for MaRDMO's tests: RDMO's defaults with MaRDMO installed.

The MaRDI Portal URLs are the real ones, so the tests read the same
items.json and properties.json as production; network requests are
blocked by pytest-socket (see pyproject.toml), the tests use recorded
answers instead.  The OAuth2 credentials are dummies.
'''
import getpass
import os
from pathlib import Path

from rdmo.core.settings import *  # noqa: F401,F403  (RDMO's defaults)
from rdmo.core.settings import INSTALLED_APPS, PROJECT_EXPORTS, _

BASE_DIR = Path(__file__).parent
MEDIA_ROOT = BASE_DIR / 'media_root'
STATIC_ROOT = BASE_DIR / 'static_root'

SECRET_KEY = 'mardmo-tests'
DEBUG = False

# SQLite in memory; TEST_DB=postgresql or TEST_DB=mysql (MySQL or MariaDB)
# runs the tests on a server as in production.  Locally it is reached by its
# Unix socket as the user running the tests; in CI (service containers) by
# TEST_DB_HOST and TEST_DB_PORT, which pytest must allow (--allow-hosts).
# pytest-django creates and drops the test database.
TEST_DB = os.environ.get('TEST_DB', 'sqlite')
SERVER = {
    'NAME': 'mardmo_tests',
    'USER': os.environ.get('TEST_DB_USER', getpass.getuser()),
    'PASSWORD': os.environ.get('TEST_DB_PASSWORD', ''),
    'HOST': os.environ.get('TEST_DB_HOST', ''),
    'PORT': os.environ.get('TEST_DB_PORT', ''),
}
if TEST_DB == 'sqlite':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
elif TEST_DB == 'postgresql':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', **SERVER}}
elif TEST_DB == 'mysql':
    try:
        import MySQLdb  # noqa: F401  (mysqlclient, as rdmo[mysql] installs it)
    except ImportError:
        # PyMySQL needs no compiler; Django asks for the version of mysqlclient
        import pymysql
        pymysql.version_info = (2, 2, 1, 'final', 0)
        pymysql.install_as_MySQLdb()
    options = {'charset': 'utf8mb4'}
    if not SERVER['HOST']:
        options['unix_socket'] = '/run/mysqld/mysqld.sock'
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql', **SERVER,
            'OPTIONS': options,
            'TEST': {'CHARSET': 'utf8mb4', 'COLLATION': 'utf8mb4_unicode_ci'},
        }
    }
else:
    raise ValueError(f'TEST_DB={TEST_DB!r}: use sqlite, postgresql or mysql')

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
