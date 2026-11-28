'''Recorded answers of the MaRDI Portal, Wikidata and citation services.

All of MaRDMO's requests to external services go through
``requests.Session.request`` (MaRDMO.sources.http.http_session).  :func:`replay` answers
them from a JSON file in tests/data/recorded; a request that is not in the
file fails the test.  :func:`record` sends them for real, with a pause
before each, and writes the file::

    RECORD=1 pytest --force-enable-socket tests/db/test_hydration.py

Recording only reads; it is for new tests or when the portal data changed.
``RECORD=missing`` (with ``--force-enable-socket``) replays and sends only
the requests a recording does not have, adding them to it: for a change
that asks a little more, without recording everything again.
A request is found again by method, URL, parameters and body; the order of
the items in a SPARQL ``VALUES`` block and in ``ids=Q1|Q2`` does not count,
because MaRDMO collects them in sets.  A recording holds the requests of all
tests that use it; recording again replaces it.  Each entry keeps the request
as sent (``request``), so the live check (tests/live) can send it again.
'''
import json
import os
import re
import threading
import time
from pathlib import Path

import requests
from requests.structures import CaseInsensitiveDict

from MaRDMO.sources.http import SPARQL_RETRY_STATUS

FOLDER = Path(__file__).parent.parent / 'data' / 'recorded'
PAUSE = 1
REAL_REQUEST = requests.Session.request
# Recordings written in this test run: later tests add their requests
_WRITTEN = set()
# A service that is down for a moment answers like this; such an answer is never recorded, else a
# test would replay the outage for good (a 502 of the portal's TeX check, 2026-11-28)
TRANSIENT = SPARQL_RETRY_STATUS
VALUES_BLOCK = re.compile(r'(VALUES\s+\?\w+\s*\{)([^}]*)(\})')


def _sorted_values(match):
    return f'{match[1]} {" ".join(sorted(match[2].split()))} {match[3]}'


def key(method, url, params=None, data=None):
    '''The request as a string that does not depend on the order of collected items.'''
    params = {name: '|'.join(sorted(str(value).split('|'))) for name, value in (params or {}).items()}
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    if isinstance(data, str):
        data = ' '.join(VALUES_BLOCK.sub(_sorted_values, data).split())
    elif data is not None:
        data = sorted(data.items()) if isinstance(data, dict) else data
    return json.dumps([method.upper(), url, sorted(params.items()), data], ensure_ascii=False)


def sent(method, params=None, data=None, headers=None):
    '''The request as MaRDMO sent it (the key leaves out line breaks, headers and the order of items).'''
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    return {'method': method.upper(), 'params': dict(params or {}), 'data': data, 'headers': dict(headers or {})}


def _response(entry):
    response = requests.Response()
    response.status_code = entry['status']
    response.headers = CaseInsensitiveDict({'Content-Type': entry['content_type']})
    response._content = entry['body'].encode('utf-8')
    response.encoding = 'utf-8'
    response.url = entry['url']
    return response


def load(names):
    '''{request: answer} of the recordings *names*.'''
    answers = {}
    for name in names:
        path = FOLDER / f'{name}.json'
        assert path.exists(), f'{path.name} not recorded (see tests/support/recordings.py)'
        answers.update({entry['key']: entry for entry in json.loads(path.read_text(encoding='utf-8'))})
    return answers


def replay(monkeypatch, names, missing):
    '''Answer every request from the recordings tests/data/recorded/<name>.json of *names*.

    A request that is not recorded raises an error and is added to
    *missing*, so it is noticed where MaRDMO catches the error.
    '''
    answers = load(names)
    path = FOLDER / f'{names[-1]}.json'

    add = os.environ.get('RECORD') == 'missing'
    lock = threading.Lock()

    def request(session, method, url, params=None, data=None, **kwargs):
        request_key = key(method, url, params, data)
        entry = answers.get(request_key)
        if entry is None and add:
            # RECORD=missing: send it for real and add it to the last recording
            time.sleep(PAUSE)
            response = REAL_REQUEST(session, method, url, params=params, data=data, **kwargs)
            if response.status_code in TRANSIENT:
                return response
            entry = {'key': request_key, 'url': url, 'status': response.status_code,
                     'content_type': response.headers.get('Content-Type', ''), 'body': response.text,
                     'request': sent(method, params, data, kwargs.get('headers'))}
            with lock:
                stored = {item['key']: item for item in json.loads(path.read_text(encoding='utf-8'))}
                stored[request_key] = answers[request_key] = entry
                path.write_text(json.dumps(sorted(stored.values(), key=lambda item: item['key']), indent=1,
                                           ensure_ascii=False) + '\n', encoding='utf-8')
        if entry is None:
            missing.append(f'{method.upper()} {url}')
            raise AssertionError(f'request not recorded in {path.name}: {method.upper()} {url} {params or ""}'
                                 f'{str(data or "")[:300]!r}')
        return _response(entry)

    monkeypatch.setattr(requests.Session, 'request', request)


def record(monkeypatch, names):
    '''Send every request for real and collect it; :func:`save` writes the file of the last name.

    Requests already in the other recordings of *names* are not stored again.
    '''
    *others, name = names
    known = load(others) if others else {}
    entries, lock = {}, threading.Lock()

    def request(session, method, url, params=None, data=None, **kwargs):
        time.sleep(PAUSE)
        response = REAL_REQUEST(session, method, url, params=params, data=data, **kwargs)
        if response.status_code in TRANSIENT:
            return response
        with lock:
            entries[key(method, url, params, data)] = {
                'key': key(method, url, params, data), 'url': url, 'status': response.status_code,
                'content_type': response.headers.get('Content-Type', ''), 'body': response.text,
                'request': sent(method, params, data, kwargs.get('headers'))}
        return response

    monkeypatch.setattr(requests.Session, 'request', request)

    def save():
        for request_key in known:
            entries.pop(request_key, None)
        path = FOLDER / f'{name}.json'
        if name in _WRITTEN:
            entries.update({entry['key']: entry for entry in json.loads(path.read_text(encoding='utf-8'))})
        _WRITTEN.add(name)
        FOLDER.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(entries.values(), key=lambda entry: entry['key']), indent=1,
                                   ensure_ascii=False) + '\n', encoding='utf-8')
    return save
