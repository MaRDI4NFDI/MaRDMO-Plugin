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
from django.core.servers.basehttp import ThreadedWSGIServer
from django.test.testcases import LiveServerThread

from MaRDMO.export.store import SESSION_JOBS_KEY

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


class OneRequestAtATime(ThreadedWSGIServer):
    '''A live server that answers one request after another, each on a connection of its own.

    RDMO's interview sends several requests at once; in a thread each, they
    would share the test's database connection at the same time.  Here the
    server thread answers them in turn (it has the test's connection), and
    closes every connection after its answer (HTTP/1.0), so a connection the
    browser keeps open does not hold up the next request.
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.RequestHandlerClass = type('Closing', (self.RequestHandlerClass,), {'protocol_version': 'HTTP/1.0'})

    def process_request(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:  # pylint: disable=broad-exception-caught
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


class InterviewServerThread(LiveServerThread):
    server_class = OneRequestAtATime


def live_server(settings, thread_class=LiveServerThread):
    '''Start a live server (*thread_class*) on the test's database connection; yield its URL.'''
    settings.ALLOWED_HOSTS = ['localhost']
    # The connection itself, not django.db.connection (a proxy to the thread's own)
    connection = connections['default']
    connection.inc_thread_sharing()
    # The static files from the apps (RDMO's and MaRDMO's styles), as StaticLiveServerTestCase
    thread = thread_class('localhost', StaticFilesHandler, connections_override={'default': connection}, port=0)
    thread.daemon = True
    thread.start()
    thread.is_ready.wait()
    if thread.error:
        raise thread.error
    yield f'http://localhost:{thread.port}'
    thread.terminate()
    connection.dec_thread_sharing()


@pytest.fixture
def server(db, settings):
    '''The URL of a live server on the test's database connection.'''
    yield from live_server(settings)


@pytest.fixture
def interview_server(db, settings):
    '''The URL of a live server for RDMO's interview (:class:`OneRequestAtATime`).'''
    yield from live_server(settings, InterviewServerThread)


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


def pages(browser, server):
    '''``(open_page, contexts)``: :func:`page_as` for *server*.'''
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
    return open_page, contexts


@pytest.fixture
def interview_as(browser, interview_server):
    ''':func:`page_as` on the :func:`interview_server`: for pages of RDMO's interview.'''
    open_page, contexts = pages(browser, interview_server)
    yield open_page
    for context in contexts:
        context.close()


@pytest.fixture
def page_as(browser, server):
    '''``page_as(user, jobs=(), language='en')``: a browser page logged in as *user*.

    It has the session cookie of Django's test client; *jobs* are export
    jobs of this session (as if it had started them), *language* is the
    browser's language.
    '''
    open_page, contexts = pages(browser, server)
    yield open_page
    for context in contexts:
        context.close()
