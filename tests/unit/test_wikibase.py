'''MaRDMO's one way to wbgetentities (MaRDMO.sources.wikibase, #198): strict and resilient.

Strict (the export's checks, the duplicate and DOI lookups) raises when a
chunk fails; resilient (the hydration) retries longer, bisects a chunk that
keeps timing out, opens a circuit breaker after dead chunks in a row, and
returns what resolved.  A fake portal answers in turn; time passes only in
requests and pauses.
'''
import pytest
import requests

import MaRDMO.sources.http as http
import MaRDMO.sources.wikibase as wikibase
from MaRDMO.sources.wikibase import HYDRATION, WikibaseError, get_entities

API = 'https://portal.example.org/w/api.php'


class Response:
    def __init__(self, status=200, body=None, retry_after=None):
        self.status_code, self.body = status, body
        self.headers = {'Retry-After': str(retry_after)} if retry_after is not None else {}

    def json(self):
        if self.body is None:
            raise ValueError('not JSON')
        return self.body


def entities(*qids):
    return Response(body={'entities': {qid: {'id': qid} for qid in qids}})


class Portal:
    '''Answers requests in turn: a Response, or an exception to raise; notes the asked QIDs and the pauses.'''

    def __init__(self, monkeypatch, *answers, timeout_takes=None):
        self.answers, self.asked, self.slept, self.timeouts = list(answers), [], [], []
        self.now, self.timeout_takes = 1000.0, timeout_takes
        monkeypatch.setattr(http, 'http_session', lambda: self)
        monkeypatch.setattr(http, 'time', self)
        monkeypatch.setattr(wikibase, 'time', self)
        monkeypatch.setattr(http.random, 'uniform', lambda low, high: 0.0)
        monkeypatch.setattr(wikibase, '_breakers', {})

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def request(self, method, url, **kwargs):
        self.asked.append(kwargs['params']['ids'])
        self.timeouts.append(kwargs['timeout'])
        answer = self.answers.pop(0)
        if isinstance(answer, requests.exceptions.Timeout):
            self.now += kwargs['timeout'] if self.timeout_takes is None else self.timeout_takes
            raise answer
        if isinstance(answer, Exception):
            raise answer
        return answer


# --- strict ---------------------------------------------------------------------------------------

def test_strict_asks_in_chunks_of_fifty(monkeypatch):
    qids = [f'Q{n}' for n in range(1, 52)]
    portal = Portal(monkeypatch, entities(*qids[:50]), entities('Q51'))
    assert set(get_entities(API, qids, 'claims')) == set(qids)
    assert [len(ids.split('|')) for ids in portal.asked] == [50, 1]


@pytest.mark.parametrize('answer', [Response(500), Response(body={'error': {'code': 'internal_api_error'}})])
def test_strict_raises_when_the_portal_does_not_give_the_entities(monkeypatch, answer):
    '''An error answer is "the portal did not answer", never "the portal has nothing".'''
    Portal(monkeypatch, answer)
    with pytest.raises(WikibaseError):
        get_entities(API, ['Q1'], 'claims')


def test_strict_uses_the_callers_waits(monkeypatch):
    portal = Portal(monkeypatch, Response(503), entities('Q1'))
    assert get_entities(API, ['Q1'], 'claims', waits=(2,)) == {'Q1': {'id': 'Q1'}}
    assert portal.slept == [2]


# --- resilient (hydration) ------------------------------------------------------------------------

def test_resilient_retries_a_server_error_and_an_error_answer(monkeypatch):
    portal = Portal(monkeypatch, Response(500), Response(body={'error': {'code': 'DBConnectionError'}}),
                    entities('Q1'))
    assert get_entities(API, ['Q1'], 'claims', resilient=True) == {'Q1': {'id': 'Q1'}}
    assert portal.slept == list(HYDRATION.waits[:2])


def test_resilient_waits_as_long_as_the_portal_asks_up_to_its_limit(monkeypatch):
    portal = Portal(monkeypatch, Response(503, retry_after=3), Response(503, retry_after=600), entities('Q1'))
    get_entities(API, ['Q1'], 'claims', resilient=True)
    assert portal.slept == [3, HYDRATION.max_retry_after]


def test_resilient_bisects_a_chunk_that_keeps_timing_out(monkeypatch):
    '''Q2 never answers (the portal gives up after 2 s): the chunk is halved until Q1 is found without it.'''
    timeout = requests.exceptions.Timeout()
    portal = Portal(monkeypatch, *[timeout] * 4, entities('Q1'), *[timeout] * 4, timeout_takes=2)
    assert get_entities(API, ['Q1', 'Q2'], 'claims', resilient=True) == {'Q1': {'id': 'Q1'}}
    assert portal.asked[4:6] == ['Q1', 'Q2']


def test_resilient_gives_up_at_its_deadline(monkeypatch):
    '''No attempt runs past the deadline: each timeout is shortened to what is left.'''
    portal = Portal(monkeypatch, *[requests.exceptions.Timeout()] * 10)
    assert get_entities(API, ['Q1'], 'claims', resilient=True) == {}
    assert portal.now <= 1000.0 + HYDRATION.deadline + 1
    assert portal.timeouts[0] == HYDRATION.timeout and portal.timeouts[-1] < HYDRATION.timeout


def test_the_breaker_opens_after_dead_chunks_and_closes_after_its_cooldown(monkeypatch):
    dead = [Response(500)] * (len(HYDRATION.waits) + 1)
    qids = [f'Q{n}' for n in range(1, 50 * HYDRATION.trip + 1)]
    portal = Portal(monkeypatch, *dead * HYDRATION.trip, entities('Q1'))
    assert get_entities(API, qids, 'claims', resilient=True) == {}
    asked = len(portal.asked)
    # Open: nothing is asked
    assert get_entities(API, ['Q1'], 'claims', resilient=True) == {} and len(portal.asked) == asked
    # After the cooldown: asked again
    portal.now += HYDRATION.cooldown
    assert get_entities(API, ['Q1'], 'claims', resilient=True) == {'Q1': {'id': 'Q1'}}


def test_a_chunk_that_answers_resets_the_streak(monkeypatch):
    dead = [Response(500)] * (len(HYDRATION.waits) + 1)
    portal = Portal(monkeypatch, *dead, entities(*[f'Q{n}' for n in range(51, 101)]), *dead)
    qids = [f'Q{n}' for n in range(1, 151)]
    assert len(get_entities(API, qids, 'claims', resilient=True)) == 50
    assert not wikibase._breaker_open(API) and len(portal.asked) == 2 * len(dead) + 1
