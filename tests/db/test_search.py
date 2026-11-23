'''The search catalog: a SPARQL query on the MaRDI Portal from the user's filters (#138).

Each mode (workflows, models, algorithms) builds its query from the
selected items and keywords.  One real query per mode was sent to the
portal and recorded (``search_*``), so the queries are valid SPARQL and
find what they should; the rest is checked on the query alone.
'''
import pytest

from MaRDMO.core.config import get_options
from MaRDMO.search import worker

OPTIONS = get_options()
EGYPTIAN_OBJECTS, SIS_MODEL, QUICKSORT = 'Q6032641', 'Q6675171', 'Q6825489'


def item(qid, name):
    return {'ID': f'mardi:{qid}', 'Name': name, 'Description': 'an item of the portal'}


def answers(mode, **filters):
    return {'search': {'options': OPTIONS[mode], **filters}}


def links(result):
    return {url.rsplit('Item:', 1)[1] for _, url in result['links']}


# --- Real queries (recorded) --------------------------------------------------------------------

def test_workflows_by_data_set(portal):
    '''The data set read by the first process step of the Egyptian objects workflow.'''
    portal('search_workflow')
    result = worker.search(answers('InterdisciplinaryWorkflow', **{
        'data-set': {0: item('Q6486605', 'Objects from the Cachette de Karnak')}}), OPTIONS)
    assert EGYPTIAN_OBJECTS in links(result) and not result['search_failed']
    assert result['no_results'] == str(len(result['links']))


def test_models_by_formula(portal):
    portal('search_model')
    result = worker.search(answers('MathematicalModel', **{
        'formula': {0: item('Q6674293', 'rate of change of infectious in the SIS model')}}), OPTIONS)
    assert SIS_MODEL in links(result)


def test_algorithms_by_algorithmic_task(portal):
    portal('search_algorithm')
    result = worker.search(answers('Algorithm', **{
        'algorithmic-task': {0: item('Q6825656', 'Sorting items under a total order')}}), OPTIONS)
    assert QUICKSORT in links(result)


# --- The query ----------------------------------------------------------------------------------

@pytest.fixture
def sent(monkeypatch):
    '''The queries sent; the portal answers *sent['rows']* (``None``: the query failed).'''
    log = {'queries': [], 'rows': [{'label': {'value': 'found'}, 'qid': {'value': 'Q1'}}]}

    def query(text, url, strict=False):
        log['queries'].append(text)
        return log['rows']
    monkeypatch.setattr(worker, 'query_sparql', query)
    return log


WORKFLOW_FILTERS = {key: {0: item(f'Q{index}', f'{key} 1'), 1: item(f'Q{index + 10}', f'{key} 2')}
                    for index, key in enumerate(['academic-discipline', 'mathematical-model', 'algorithm',
                                                 'software', 'hardware', 'method', 'instrument', 'data-set'],
                                                start=101)}
MODEL_FILTERS = {key: {0: item(f'Q{index}', f'{key} 1')}
                 for index, key in enumerate(['research-problem', 'academic-discipline', 'computational-task',
                                              'formula', 'quantity'], start=201)}


@pytest.mark.parametrize('mode, filters', [
    ('InterdisciplinaryWorkflow', {**WORKFLOW_FILTERS, 'research-objective': {0: 'rules', 1: 'objects'}}),
    ('MathematicalModel', {**MODEL_FILTERS, 'mathematical-model-properties': {
        0: 'https://rdmo.mardi4nfdi.de/terms/options/mathmoddb/is-linear'}}),
    ('Algorithm', {'algorithmic-task': {0: item('Q301', 'task')}, 'software': {0: item('Q302', 'software')}}),
])
def test_every_filter_is_in_the_query(sent, mode, filters):
    result = worker.search(answers(mode, **filters), OPTIONS)
    query, = sent['queries']
    for values in filters.values():
        for value in values.values():
            if isinstance(value, dict):
                assert f'wd:{value["ID"].split(":")[1]}' in query, value
                assert value['Name'] in query
    assert result['no_results'] == '1' and result['links'] == [['found', 'https://portal.mardi4nfdi.de/wiki/Item:Q1']]
    # The query is shown escaped, line by line
    assert '<br>' in result['query'] and '<' not in result['query'].replace('<br>', '')


def test_a_keyword_cannot_break_out_of_the_query(sent):
    worker.search(answers('InterdisciplinaryWorkflow', **{
        'research-objective': {0: 'rules" } } DROP ALL #\nnext line'}}), OPTIONS)
    query, = sent['queries']
    assert 'rules\\" } } drop all #\\nnext line' in query          # one string literal, lower case
    # The comment naming the keyword stays on one line
    assert '# research objective: rules" } } DROP ALL # next line\n' in query


@pytest.mark.parametrize('mode', ['InterdisciplinaryWorkflow', 'MathematicalModel', 'Algorithm'])
def test_no_filter_sends_no_query(sent, mode):
    result = worker.search(answers(mode), OPTIONS)
    assert sent['queries'] == [] and 'no parameters defined' in result['query'] and result['links'] == []


def test_items_without_portal_id_are_left_out(sent):
    '''A new item or a Wikidata item has no QID on the portal: the search cannot use it.'''
    result = worker.search(answers('Algorithm', **{'algorithmic-task': {
        0: {'ID': 'user:0b5c', 'Name': 'mine'}, 1: {'ID': 'wikidata:Q42', 'Name': 'theirs'}}}), OPTIONS)
    assert sent['queries'] == [] and 'no usable parameters' in result['query']


def test_a_failed_query_is_not_zero_results(sent):
    sent['rows'] = None
    result = worker.search(answers('Algorithm', **{'software': {0: item('Q302', 'software')}}), OPTIONS)
    assert result['search_failed'] and result['links'] == [] and result['no_results'] == '0'


def test_an_unknown_mode_changes_nothing(sent):
    result = worker.search({'search': {'options': 'https://example.org/other'}}, OPTIONS)
    assert sent['queries'] == [] and result['query'] == '' and not result['search_failed']
