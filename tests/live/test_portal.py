'''Read-only check of the MaRDI Portal and Wikidata: do they still answer as recorded? (#93)

The recordings (tests/recordings.py) hold the requests MaRDMO sends: entity
searches, SPARQL queries, TeX checks.  Each is sent again, one per second,
and its answer is compared with the recorded one by structure, not by value,
so that ordinary edits on the portal do not count:

- the same status code;
- the keys of every recorded object are still there;
- a list with entries (search hits, SPARQL rows) still has entries;
- the same SPARQL result variables, and the same result of a TeX check.

A recorded error that now succeeds is not a failure but a note: record
again.  The dropdown searches, which the tests replace, are run live too.
Only reading requests are sent (READ_ONLY)::

    LIVE=1 pytest tests/live --force-enable-socket

LIVE_REPORT=<file> writes what changed as Markdown (the nightly workflow
puts it in the run's summary and its issue).
'''
import json
import os
import time

import pytest
import requests

from MaRDMO import queries
from MaRDMO.constants import TEX_CHECK_URL
from MaRDMO.getters import get_items, get_url
from tests.recordings import FOLDER, REAL_REQUEST

pytestmark = pytest.mark.skipif(os.environ.get('LIVE') != '1', reason='live check: LIVE=1 (see module docstring)')

PAUSE = 1
API_ACTIONS = {'wbsearchentities', 'wbgetentities', 'query'}
# Problems and notes of this run, for LIVE_REPORT (tests/live/conftest.py)
REPORT = {'problems': [], 'notes': []}


def recorded():
    '''Every recorded request once: [(recording, entry)].'''
    entries = {}
    for path in sorted(FOLDER.glob('*.json')):
        for entry in json.loads(path.read_text(encoding='utf-8')):
            entries.setdefault(entry['key'], (path.stem, entry))
    return list(entries.values())


def read_only(url, request):
    '''Whether *request* to *url* only reads: searches, SPARQL queries and TeX checks.'''
    if request['method'] == 'GET':
        return url.endswith('/api.php') and request['params'].get('action') in API_ACTIONS
    return url.endswith('/sparql') or url == TEX_CHECK_URL


def compare(recorded_value, live_value, path=''):
    '''What changed in the structure of *live_value* against *recorded_value*.'''
    if isinstance(recorded_value, dict):
        if not isinstance(live_value, dict):
            return [f'{path or "/"}: an object became {type(live_value).__name__}']
        problems = []
        for name, value in recorded_value.items():
            if name not in live_value:
                problems.append(f'{path}/{name}: missing')
            elif name == 'vars' and path == '/head':
                if value != live_value[name]:
                    problems.append(f'/head/vars: {value} -> {live_value[name]}')
            elif name == 'success':
                if value != live_value[name]:
                    problems.append(f'{path}/success: {value} -> {live_value[name]}')
            else:
                problems += compare(value, live_value[name], f'{path}/{name}')
        return problems
    if isinstance(recorded_value, list):
        if not isinstance(live_value, list):
            return [f'{path}: a list became {type(live_value).__name__}']
        if recorded_value and not live_value:
            return [f'{path}: no entries any more ({len(recorded_value)} recorded)']
    return []


def describe(recording, entry):
    request = entry['request']
    what = request['params'].get('action') or ('SPARQL' if entry['url'].endswith('/sparql') else 'TeX check')
    detail = request['params'].get('search') or request['params'].get('ids') or str(request['data'] or '')[:80]
    return f'{recording}: {what} {detail!r}'


@pytest.mark.parametrize('recording, entry', [pytest.param(recording, entry, id=f'{recording}-{index}')
                                              for index, (recording, entry) in enumerate(recorded())])
def test_the_portal_answers_as_recorded(recording, entry):
    assert 'request' in entry, f'{recording}: recorded without the request; record again (tests/recordings.py)'
    request, url = entry['request'], entry['url']
    assert read_only(url, request), f'{describe(recording, entry)}: not a reading request, not sent'
    time.sleep(PAUSE)
    data = request['data'].encode('utf-8') if isinstance(request['data'], str) else request['data']
    response = REAL_REQUEST(requests.Session(), request['method'], url, params=request['params'] or None,
                            data=data, headers=request.get('headers') or {}, timeout=60)
    if response.status_code != entry['status']:
        if entry['status'] >= 400 and response.status_code == 200:
            REPORT['notes'].append(f'{describe(recording, entry)}: now answers (was {entry["status"]}); '
                                   'record again')
            return
        problems = [f'status {entry["status"]} -> {response.status_code}']
    elif entry['status'] >= 400:
        return
    else:
        try:
            problems = compare(json.loads(entry['body']), response.json())
        except ValueError:
            problems = ['the answer is not JSON any more']
    if problems:
        REPORT['problems'].append(f'{describe(recording, entry)}: ' + '; '.join(problems))
    assert not problems, problems


# The dropdown searches the provider tests replace: (search, item classes)
SEARCHES = [('concentration', ['quantity', 'kind of quantity']), ('euler', ['algorithm']), ('pyt', ['software'])]


@pytest.mark.parametrize('search, classes', SEARCHES, ids=[search for search, _ in SEARCHES])
def test_the_dropdown_searches_find_items(search, classes):
    items = get_items()
    time.sleep(PAUSE)
    mardi = queries.query_api_per_class(search, [items[name] for name in classes], raise_errors=True)
    time.sleep(PAUSE)
    wikidata = queries.query_api(get_url('wikidata', 'api'), search, raise_errors=True)
    problems = []
    if not mardi or not all(option['id'].startswith('mardi:Q') and option['text'] for option in mardi):
        problems.append(f'MaRDI Portal: {mardi[:2]}')
    if not wikidata or not all({'id', 'display'} <= hit.keys() for hit in wikidata):
        problems.append(f'Wikidata: {wikidata[:2]}')
    if problems:
        REPORT['problems'].append(f'dropdown search {search!r}: ' + '; '.join(problems))
    assert not problems, problems
