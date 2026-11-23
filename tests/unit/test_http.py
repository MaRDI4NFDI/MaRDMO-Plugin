'''MaRDMO's requests to external services (MaRDMO.sources.http, .sparql, #198): where they fail.

A failed SPARQL query is "no rows" (``[]``), or with *strict* "did not
answer" (``None``), whatever went wrong; a split query fills no item half;
a retry that would end past the deadline is not started.  A fake endpoint
answers in turn; time passes only in requests and pauses.
'''
import pytest
import requests

import MaRDMO.sources.http as http
from MaRDMO.sources.sparql import query_sparql, query_sparql_parts
from MaRDMO.sources.http import request_with_retry

ENDPOINT = 'https://sparql.example.org/query'


class Response:
    def __init__(self, status=200, body=None, text=''):
        self.status_code, self.body, self.text, self.headers = status, body, text, {}

    def json(self):
        if self.body is None:
            raise ValueError('not JSON')
        return self.body


def rows(*ids, **columns):
    return Response(body={'results': {'bindings': [
        {'id': {'value': id_}, **{name: {'value': f'{name} of {id_}'} for name in columns}} for id_ in ids
    ]}})


class Endpoint:
    '''Answers requests in turn: a Response, or an exception to raise; notes the pauses.'''

    def __init__(self, monkeypatch, *answers):
        self.answers, self.slept, self.now = list(answers), [], 1000.0
        monkeypatch.setattr(http, 'http_session', lambda: self)
        monkeypatch.setattr(http, 'time', self)

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def request(self, method, url, **kwargs):
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


# --- request_with_retry ---------------------------------------------------------------------------

def test_a_retry_past_the_deadline_is_not_started_and_the_answer_returned(monkeypatch):
    endpoint = Endpoint(monkeypatch, Response(503), Response(200))
    response = request_with_retry('get', ENDPOINT, waits=(5,), deadline=1003.0, retry_status=(503,))
    assert response.status_code == 503 and endpoint.slept == []


def test_a_retry_past_the_deadline_is_not_started_and_the_error_raised(monkeypatch):
    endpoint = Endpoint(monkeypatch, requests.exceptions.ConnectionError(), Response(200))
    with pytest.raises(requests.exceptions.ConnectionError):
        request_with_retry('get', ENDPOINT, waits=(5,), deadline=1003.0)
    assert endpoint.slept == []


# --- query_sparql ---------------------------------------------------------------------------------

def test_the_bindings_of_an_answer(monkeypatch):
    Endpoint(monkeypatch, rows('Q1'))
    assert query_sparql('SELECT', ENDPOINT) == [{'id': {'value': 'Q1'}}]


@pytest.mark.parametrize('answers', [
    pytest.param((), id='no endpoint'),
    pytest.param((Response(400, text='syntax error'),), id='status 400'),
    pytest.param((requests.exceptions.Timeout(), requests.exceptions.Timeout()), id='timeout'),
    pytest.param((requests.exceptions.TooManyRedirects(),), id='other request error'),
    pytest.param((Response(200),), id='invalid JSON'),
])
@pytest.mark.parametrize('strict, failed', [(False, []), (True, None)])
def test_a_failed_query(monkeypatch, answers, strict, failed):
    Endpoint(monkeypatch, *answers)
    assert query_sparql('SELECT', ENDPOINT if answers else '', strict=strict) == failed


# --- query_sparql_parts ---------------------------------------------------------------------------

def test_the_parts_are_merged_per_item(monkeypatch):
    Endpoint(monkeypatch, rows('Q1', 'Q2', label=1), rows('Q2', formula=1))
    assert query_sparql_parts(['first', 'second'], ENDPOINT) == [
        {'id': {'value': 'Q1'}, 'label': {'value': 'label of Q1'}},
        {'id': {'value': 'Q2'}, 'label': {'value': 'label of Q2'}, 'formula': {'value': 'formula of Q2'}},
    ]


def test_a_failed_part_fills_no_item(monkeypatch):
    Endpoint(monkeypatch, rows('Q1', label=1), Response(400))
    assert query_sparql_parts(['first', 'second'], ENDPOINT) == []


def test_no_item_asks_no_further_part(monkeypatch):
    endpoint = Endpoint(monkeypatch, rows(), rows('Q1'))
    assert query_sparql_parts(['first', 'second'], ENDPOINT) == []
    assert len(endpoint.answers) == 1
