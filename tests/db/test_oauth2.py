'''The export through the MaRDI Portal's OAuth2 login, on RDMO's real URLs (#138).

A clean documentation (white_2006) is exported as the user does: the export
page redirects to the portal's authorization page, the portal calls RDMO's
callback (``/services/oauth/<provider>/callback/``), which hands over to
MaRDMO's callback; that exchanges the code for a token, starts the upload
and leads to the progress page.  The portal is faked: the token exchange,
and the upload with the portal of tests/db/test_upload.py.  The upload
thread is run in the test, after the callback.
'''
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from MaRDMO.store import _progress_store
from tests.db.conftest import portal, white  # noqa: F401 (white_2006, complete; its recorded portal)
from tests.db.test_upload import Portal
from tests.support.html import export_page, text

CALLBACK = '/services/oauth/wikibase/callback/'


def state_of(client):
    '''The state MaRDMO stored in the session when it sent the user to the portal.'''
    return next(value for key, value in client.session.items() if key.endswith('.state'))


@pytest.fixture
def token(monkeypatch):
    '''The portal's token endpoint: answers *token['answer']* (a status code and a JSON body).'''
    sent = {'answer': (200, {'access_token': 'token'}), 'requests': []}

    def post(url, data=None, auth=None, headers=None, timeout=None):
        sent['requests'].append((url, data))
        status, body = sent['answer']
        response = SimpleNamespace(status_code=status, content=str(body).encode(), json=lambda: body)

        def raise_for_status():
            if status >= 400:
                raise requests.HTTPError(f'{status} Client Error', response=response)
        response.raise_for_status = raise_for_status
        return response
    monkeypatch.setattr(requests, 'post', post)
    return sent


@pytest.fixture
def threads(monkeypatch):
    '''The upload threads the callback starts, not started: ``[(target, args)]``.'''
    started = []

    class Thread:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            started.append((self.target, self.args))
    monkeypatch.setattr('MaRDMO.oauth2.threading.Thread', Thread)
    return started


def authorized(client, documentation):
    '''Export *documentation* up to the portal's authorization page; returns its URL.'''
    response = export_page(client, documentation)
    assert response.status_code == 302, text(response.content.decode())
    return response['Location']


def test_the_export_goes_through_the_portal_login_to_the_result(white, client, token, threads, monkeypatch):  # noqa: F811
    url = urlparse(authorized(client, white))
    assert f'{url.scheme}://{url.netloc}{url.path}' == 'https://portal.mardi4nfdi.de/w/rest.php/oauth2/authorize'
    query = parse_qs(url.query)
    assert query['client_id'] == ['mardmo-tests'] and query['response_type'] == ['code']
    assert query['state'] == [state_of(client)]

    # The portal calls RDMO's callback, RDMO hands over to MaRDMO (it finds the state in the session)
    response = client.get(CALLBACK, {'state': query['state'][0], 'code': 'the-code'})
    assert response.status_code == 302 and response['Location'].startswith('/services/progress/')
    assert token['requests'][0][1] == {'client_id': 'mardmo-tests', 'client_secret': 'mardmo-tests',
                                       'grant_type': 'authorization_code', 'code': 'the-code'}
    job = response['Location'].rstrip('/').rsplit('/', 1)[1]
    assert _progress_store[job]['phase'] == 'starting'
    assert not any(key.endswith('.state') for key in client.session.keys())

    # The upload, as the thread runs it
    fake = Portal()
    sent, post = [], fake.request
    fake.request = lambda method, url, **kwargs: sent.append(kwargs.get('headers')) or post(method, url, **kwargs)
    monkeypatch.setattr('MaRDMO.upload.requests.Session', lambda: fake)
    monkeypatch.setattr('MaRDMO.upload.time.sleep', lambda seconds: None)
    # The thread closes its own database connection at the end; run in the test's thread it
    # would close the test's (PostgreSQL and MariaDB refuse queries after that, SQLite reconnects)
    monkeypatch.setattr('MaRDMO.upload.connection', SimpleNamespace(close=lambda: None))
    (target, args), = threads
    target(*args)
    # with the user's token
    assert sent and all(headers == {'Authorization': 'Bearer token'} for headers in sent)
    assert _progress_store[job]['phase'] == 'done', _progress_store[job].get('error')
    assert len(fake.items) == _progress_store[job]['counts']['items_created'] > 0

    # Progress and result pages of this session
    status = client.get(f'/services/progress/{job}/status/').json()
    assert status['done'] and status['progress'] == 100
    assert client.get(f'/services/progress/{job}/').status_code == 200
    result = client.get(f'/services/success/{job}/')
    assert result.status_code == 200 and 'opiate' in text(result.content.decode())
    # The created items are the project's now: their pages have portal IDs
    assert white.values.filter(snapshot=None, external_id__startswith='mardi:Q90000').exists()


def test_a_callback_with_another_state_is_refused(white, client, token, threads):  # noqa: F811
    authorized(client, white)
    response = client.get(CALLBACK, {'state': 'forged', 'code': 'the-code'})
    page = text(response.content.decode())
    assert 'OAuth authorization not successful' in page and 'State parameter did not match' in page
    assert token['requests'] == [] and threads == []


def test_a_callback_without_login_is_an_integration_error(white, client, token, threads):  # noqa: F811
    '''No state in the session: RDMO finds no provider that started a login.'''
    response = client.get(CALLBACK, {'state': 'any', 'code': 'the-code'})
    assert response.status_code == 500 and token['requests'] == [] and threads == []


def test_a_refused_token_exchange_is_reported(white, client, token, threads):  # noqa: F811
    token['answer'] = (401, {'error': 'invalid_client'})
    authorized(client, white)
    response = client.get(CALLBACK, {'state': state_of(client), 'code': 'the-code'})
    assert 'OAuth process failed' in text(response.content.decode()) and threads == []


def test_a_login_without_export_request_is_reported(white, client, token, threads):  # noqa: F811
    '''The session lost the export (e.g. a second callback): nothing is uploaded.'''
    authorized(client, white)
    state = state_of(client)
    session = client.session
    for key in [key for key in session.keys() if key.endswith('.request')]:
        del session[key]
    session.save()
    response = client.get(CALLBACK, {'state': state, 'code': 'the-code'})
    assert 'But no redirect could be found' in text(response.content.decode()) and threads == []
