'''The upload when the MaRDI Portal does not simply accept (#138).

The real upload (upload.Upload.run) posts a small export (two new
items, a statement on the first) to a portal that answers from a script:
rate limits, refusals, server errors, timeouts, rejected values, an item
that exists already.  What the user reads afterwards is the progress
store's result: done, partial (something was created) or error (nothing
was), with a message that says what happened.
'''
import json
from types import SimpleNamespace

import pytest
import requests

from MaRDMO.portal_errors import extract_error_message
from MaRDMO.store import _progress_store
from MaRDMO.upload import Upload, retry_after_seconds

URI = 'https://portal.mardi4nfdi.de/w/rest.php/wikibase/v1/entities/items'
OK = 'ok'


def item(label, statements=()):
    statements = [list(st) for st in statements]
    return {'id': '', 'label': label, 'description': f'{label} of the tests', 'url': URI, 'statements': statements,
            'user_ids': [], 'payload': {'item': {
                'labels': {'en': label}, 'descriptions': {'en': f'{label} of the tests'},
                'statements': {pid: [{'property': {'id': pid, 'data_type': dtype},
                                      'value': {'type': 'value', 'content': value}}]
                               for pid, dtype, value, _ in statements}}}}


def export():
    return {
        'Item0000000001': item('flux model', [('P27', 'external-id', '10.1000/x', [])]),
        'Item0000000002': item('flux task'),
        'RELATION0': {'id': '', 'exists': 'false', 'url': f'{URI}/Item0000000001/statements',
                      'payload': {'statement': {'property': {'id': 'P1460', 'data_type': 'wikibase-item'},
                                                'value': {'type': 'value', 'content': 'Item0000000002'}}}},
    }


class Portal:
    '''A session that answers from *script*: ``'ok'``, ``'timeout'``, or ``(status, body, headers)``.'''

    def __init__(self, *script):
        self.script, self.sent, self.created = list(script), [], 0

    def request(self, method, url, json=None, headers=None, timeout=None):  # noqa: A002 (as requests)
        self.sent.append((method, url, json))
        answer = self.script.pop(0) if self.script else OK
        if answer == 'timeout':
            raise requests.exceptions.Timeout('read timeout')
        if answer == OK:
            self.created += 1
            status, body, headers_ = 200, {'id': f'Q{900 + self.created}'}, {}
        else:
            status, body, headers_ = answer
        response = SimpleNamespace(status_code=status, headers=headers_, text=globals()['json'].dumps(body),
                                   json=lambda: body)

        def raise_for_status():
            if status >= 400:
                raise requests.HTTPError(f'{status}', response=response)
        response.raise_for_status = raise_for_status
        return response


@pytest.fixture
def upload(db, monkeypatch):
    '''Upload the export to a portal with the given script; returns ``(result, portal, slept)``.'''
    slept = []
    monkeypatch.setattr('MaRDMO.upload.time.sleep', slept.append)

    def run(*script):
        upload = Upload('job', {'Authorization': 'Bearer token'}, Portal(*script))
        upload.run(SimpleNamespace(build_absolute_uri=lambda path: path), export(),
                   ['Item0000000002', 'Item0000000001'], None)
        return _progress_store['job'], upload.session, slept
    return run


def test_everything_accepted(upload):
    result, portal, _ = upload()
    assert result['phase'] == 'done' and result['counts']['items_created'] == 2
    # The statement names the created items by their new QIDs
    method, url, body = portal.sent[2]
    assert url.endswith('/Q902/statements') and body['statement']['value']['content'] == 'Q901'


def test_a_rate_limit_waits_as_the_portal_asks(upload):
    result, portal, slept = upload((429, {'message': 'slow down'}, {'Retry-After': '7'}))
    assert result['phase'] == 'done' and 7 in slept and len(portal.sent) == 4


@pytest.mark.parametrize('status, expected', [
    (403, 'refused the request 5 times'),
    (503, 'did not accept the request after 5 attempts'),
])
def test_a_portal_that_keeps_refusing_stops_before_anything_is_created(upload, status, expected):
    result, portal, _ = upload(*[(status, {'message': 'busy'}, {})] * 5)
    assert result['phase'] == 'error' and expected in result['error'] and portal.created == 0


def test_a_portal_that_does_not_answer(upload):
    result, _, _ = upload(*['timeout'] * 5)
    assert result['phase'] == 'error' and 'could not be reached' in result['error']


def test_a_temporary_error_is_retried(upload):
    result, _, _ = upload('timeout', (503, {}, {}), (403, {}, {}))
    assert result['phase'] == 'done' and result['counts']['items_created'] == 2


def test_an_item_that_exists_already_stops_the_export(upload):
    duplicate = (422, {'code': 'data-policy-violation', 'context': {
        'violation': 'item-label-description-duplicate',
        'violation_context': {'conflicting_item_id': 'Q42'}}}, {})
    result, _, _ = upload(OK, duplicate)
    # The task was created, the model is a duplicate: partial, and the message names it
    assert result['phase'] == 'partial' and 'flux model' in result['error'] and 'Q42' in result['error']
    assert result['counts']['items_created'] == 1


def test_another_policy_violation_stops_the_export(upload):
    result, _, _ = upload((422, {'code': 'data-policy-violation', 'context': {'violation': 'something-else'}}, {}))
    assert result['phase'] == 'error' and 'rejected the request (HTTP 422)' in result['error']


def test_a_rejected_value_is_named(upload):
    '''The portal names the field it rejects: the message names property, value and item.'''
    invalid = (400, {'code': 'invalid-value', 'message': "Invalid value at '/item/statements/P27/0/value/content'"}, {})
    result, _, _ = upload(OK, invalid)
    assert result['phase'] == 'partial'
    assert "'10.1000/x'" in result['error'] and 'DOI' in result['error'] and "'flux model'" in result['error']


def test_an_error_in_a_statement_keeps_the_created_items(upload):
    result, _, _ = upload(OK, OK, (400, {'message': 'bad statement'}, {}))
    assert result['phase'] == 'partial' and result['counts']['items_created'] == 2
    assert result['counts']['relations_created'] == 0 and result['counts']['relations_planned'] == 1
    assert 'bad statement' in result['error']


@pytest.mark.parametrize('header, seconds', [('12', 12), ('soon', 5), ('600', 60), ('0', 1)])
def test_retry_after(header, seconds):
    response = SimpleNamespace(headers={'Retry-After': header})
    assert retry_after_seconds(response) == seconds


@pytest.mark.parametrize('body, text', [
    ({'message': 'REST message'}, 'REST message'),
    ({'error': {'info': 'Action API info'}}, 'Action API info'),
    ({'code': 'some-code', 'context': {'a': 1}}, 'some-code (a: 1)'),
])
def test_error_messages_of_both_apis(body, text):
    response = SimpleNamespace(json=lambda: body, text=json.dumps(body))
    assert extract_error_message(response) == text
