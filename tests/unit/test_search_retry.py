'''The dropdown search is retried once on a quick failure, not after a timeout (#94).'''
import pytest
import requests

import MaRDMO.queries as queries
from MaRDMO.getters import get_items, get_url

SEARCH = {'query': {'search': [{'title': 'Item:Q1'}]}}
ENTITIES = {'entities': {'Q1': {'labels': {'en': {'value': 'alpha'}}, 'descriptions': {'en': {'value': 'first'}}}}}
WIKIDATA = {'search': [{'id': 'Q2', 'display': {'label': {'value': 'alpha'}, 'description': {'value': 'second'}}}]}


class Response:
    def __init__(self, status=200, body=None):
        self.status_code, self.body, self.headers = status, body or {}, {}

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f'status {self.status_code}')


class Portal:
    '''Answers requests in turn: a Response, or an exception to raise.  Time passes only in requests.'''

    def __init__(self, monkeypatch, *answers, takes=0.0):
        self.answers, self.requests, self.timeouts = list(answers), [], []
        self.now, self.takes = 1000.0, takes
        monkeypatch.setattr(queries, 'http_session', lambda: self)
        # A clock of MaRDMO's queries only: threads and pytest keep the real one
        monkeypatch.setattr(queries, 'time', self)

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def request(self, method, url, **kwargs):
        self.requests.append(kwargs['params'].get('action'))
        self.timeouts.append(kwargs['timeout'])
        answer = self.answers.pop(0)
        self.now += kwargs['timeout'] if isinstance(answer, requests.exceptions.Timeout) else self.takes
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def search():
    '''The MaRDI part of a dropdown search for quantities.'''
    items = get_items()
    return lambda: queries.query_api_per_class('alpha', [items['quantity'], items['kind of quantity']],
                                               raise_errors=True)


def test_a_connection_error_is_retried(monkeypatch, search):
    portal = Portal(monkeypatch, requests.exceptions.ConnectionError(), Response(body=SEARCH),
                    Response(body=ENTITIES))
    assert search() == [{'id': 'mardi:Q1', 'text': 'alpha (first)'}]
    assert portal.requests == ['query', 'query', 'wbgetentities']


@pytest.mark.parametrize('status', [429, 502, 503, 504])
def test_an_overloaded_portal_is_asked_again(monkeypatch, search, status):
    portal = Portal(monkeypatch, Response(body=SEARCH), Response(status), Response(body=ENTITIES))
    assert search() == [{'id': 'mardi:Q1', 'text': 'alpha (first)'}]
    assert portal.requests == ['query', 'wbgetentities', 'wbgetentities']


def test_a_failure_after_four_seconds_is_retried_within_the_time_of_one_request(monkeypatch, search):
    '''The retry gets the time left until SEARCH_TIMEOUT + SEARCH_RETRY_WAIT (at least 1 s).'''
    portal = Portal(monkeypatch, Response(502), Response(body=SEARCH), Response(body=ENTITIES), takes=4)
    search()
    assert portal.requests == ['query', 'query', 'wbgetentities']
    assert portal.timeouts == [queries.SEARCH_TIMEOUT, 1, queries.SEARCH_TIMEOUT]


def test_a_timeout_is_not_retried(monkeypatch, search):
    portal = Portal(monkeypatch, requests.exceptions.Timeout())
    start = portal.now
    with pytest.raises(requests.exceptions.Timeout):
        search()
    assert portal.requests == ['query']
    assert portal.now - start == queries.SEARCH_TIMEOUT


def test_a_second_failure_shows_no_results_and_is_not_cached(monkeypatch):
    portal = Portal(monkeypatch, Response(503), Response(503), Response(body=SEARCH), Response(body=ENTITIES))
    assert queries.query_sources('alpha', get_items()['quantity'], sources=['mardi'], not_found=False) == []
    assert queries.query_sources('alpha', get_items()['quantity'], sources=['mardi'], not_found=False) == [
        {'id': 'mardi:Q1', 'text': 'alpha (first)', 'help': '<strong class="text-muted">[mardi]</strong>'}]
    assert portal.requests == ['query', 'query', 'query', 'wbgetentities']


def test_the_wikidata_search_is_retried_too(monkeypatch):
    portal = Portal(monkeypatch, requests.exceptions.ConnectionError(), Response(body=WIKIDATA))
    assert queries.query_sources('alpha', [], sources=['wikidata'], not_found=False) == [
        {'id': 'wikidata:Q2', 'text': 'alpha (second)', 'help': '<strong class="text-muted">[wikidata]</strong>'}]
    assert portal.requests == ['wbsearchentities', 'wbsearchentities']


def test_the_export_check_keeps_its_own_retries(monkeypatch):
    '''query_api retries only when asked: the export's duplicate check passes its own waits.'''
    portal = Portal(monkeypatch, requests.exceptions.ConnectionError())
    assert queries.query_api(get_url('mardi', 'api'), 'alpha') == []
    assert portal.requests == ['wbsearchentities']
