'''The live check compares answers by structure, and sends only reading requests (tests/live, #93).'''
from MaRDMO.constants import TEX_CHECK_URL
from tests.live.test_portal import compare, read_only, recorded

API = 'https://portal.mardi4nfdi.de/w/api.php'


def test_values_may_change_keys_may_not():
    recorded_answer = {'search': [{'id': 'Q1', 'label': 'alpha'}], 'success': 1}
    assert compare(recorded_answer, {'search': [{'id': 'Q2'}, {'id': 'Q3'}], 'success': 1, 'new': 0}) == []
    assert compare(recorded_answer, {'search': [{'id': 'Q2'}]}) == ['/success: missing']


def test_hits_and_rows_may_not_disappear():
    assert compare({'search': [{'id': 'Q1'}]}, {'search': []}) == ['/search: no entries any more (1 recorded)']
    assert compare({'search': []}, {'search': [{'id': 'Q1'}]}) == []


def test_sparql_variables_and_tex_results_are_compared():
    sparql = {'head': {'vars': ['id', 'qid']}, 'results': {'bindings': [{'id': {}}]}}
    assert compare(sparql, {'head': {'vars': ['id']}, 'results': {'bindings': [{'id': {}}]}}) == [
        "/head/vars: ['id', 'qid'] -> ['id']"]
    assert compare({'success': True, 'checked': 'A_{m}'}, {'success': False, 'checked': ''}) == [
        '/success: True -> False']


def test_only_reading_requests_are_sent():
    assert read_only(API, {'method': 'GET', 'params': {'action': 'wbsearchentities'}, 'data': None})
    assert read_only('https://query.portal.mardi4nfdi.de/sparql', {'method': 'POST', 'params': {}, 'data': 'q'})
    assert read_only(TEX_CHECK_URL, {'method': 'POST', 'params': {}, 'data': {'q': 'x'}})
    assert not read_only(API, {'method': 'POST', 'params': {'action': 'wbeditentity'}, 'data': {}})
    assert not read_only(API, {'method': 'GET', 'params': {'action': 'wbeditentity'}, 'data': None})


def test_every_recorded_request_is_kept_and_reading():
    '''Recorded with the request as sent (tests/recordings.py), and nothing that writes.'''
    entries = recorded()
    assert entries and all('request' in entry and read_only(entry['url'], entry['request'])
                           for _, entry in entries)


def test_sparql_queries_are_kept_with_their_content_type():
    '''Sent without it, the query service answers 405.'''
    queries = [entry['request'] for _, entry in recorded() if entry['url'].endswith('/sparql')]
    assert queries and all(request['headers'].get('Content-Type', '').startswith('application/sparql-query')
                           for request in queries)
