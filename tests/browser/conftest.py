'''Browser tests: MaRDMO's pages in a real browser (Playwright with Chromium).

Opt-in, as they need a browser and open a local port:

    pip install playwright && playwright install chromium
    BROWSER=1 QUESTIONNAIRE=... pytest tests/browser --force-enable-socket

The pages come from a live server in a thread that uses the test's database
connection (as Django does for SQLite in memory), so a test sees its own
answers and everything is rolled back afterwards.  The portal is faked.
'''
import importlib.util
import os

import pytest
from django.db import connections
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.test import Client
from django.test.testcases import LiveServerThread

from MaRDMO.store import SESSION_JOBS_KEY

# The test database with the questionnaire, and the helpers to fill projects
from tests.db.conftest import django_db_setup, project  # noqa: F401

# SCREENSHOTS=<folder> saves pictures of what the tests look at (CI uploads them)
SCREENSHOTS = os.environ.get('SCREENSHOTS')


def screenshot(target, name, full_page=False):
    '''Save a picture of *target* (a page or a locator) as <SCREENSHOTS>/<name>.png, if SCREENSHOTS is set.'''
    if SCREENSHOTS:
        os.makedirs(SCREENSHOTS, exist_ok=True)
        options = {'full_page': True} if full_page else {}
        target.screenshot(path=os.path.join(SCREENSHOTS, f'{name}.png'), **options)



# Without Playwright the test modules cannot even be imported (the tests run
# without it, e.g. CI's test step); with it but without BROWSER=1 they are skipped
collect_ignore_glob = [] if importlib.util.find_spec('playwright') else ['test_*.py']


def pytest_collection_modifyitems(config, items):
    '''Without BROWSER=1 (or without Playwright) the browser tests are skipped.'''
    reason = None
    if not os.environ.get('BROWSER'):
        reason = 'browser tests run with BROWSER=1 (see tests/browser/conftest.py)'
    elif importlib.util.find_spec('playwright') is None:
        reason = 'Playwright is not installed'
    if reason:
        for item in items:
            if 'tests/browser' in str(item.fspath):
                item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def server(db, settings):
    '''The URL of a live server on the test's database connection.'''
    settings.ALLOWED_HOSTS = ['localhost']
    # The connection itself, not django.db.connection (a proxy to the thread's own)
    connection = connections['default']
    connection.inc_thread_sharing()
    # The static files from the apps (RDMO's and MaRDMO's styles), as StaticLiveServerTestCase
    thread = LiveServerThread('localhost', StaticFilesHandler, connections_override={'default': connection}, port=0)
    thread.daemon = True
    thread.start()
    thread.is_ready.wait()
    if thread.error:
        raise thread.error
    yield f'http://localhost:{thread.port}'
    thread.terminate()
    connection.dec_thread_sharing()


@pytest.fixture(scope='session')
def browser():
    from playwright.sync_api import sync_playwright
    # Playwright's sync API runs an event loop in the test's thread; the test's
    # own database calls are synchronous all the same
    os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
    with sync_playwright() as driver:
        launched = driver.chromium.launch()
        yield launched
        launched.close()


@pytest.fixture
def page_as(browser, server):
    '''``page_as(user, jobs=(), language='en')``: a browser page logged in as *user*.

    It has the session cookie of Django's test client; *jobs* are export
    jobs of this session (as if it had started them), *language* is the
    browser's language.
    '''
    contexts = []

    def open_page(user, jobs=(), language='en'):
        client = Client()
        client.force_login(user)
        if jobs:
            session = client.session
            session[SESSION_JOBS_KEY] = list(jobs)
            session.save()
        context = browser.new_context(base_url=server, locale=language)
        context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value,
                              'url': server}])
        contexts.append(context)
        return context.new_page()

    yield open_page
    for context in contexts:
        context.close()
