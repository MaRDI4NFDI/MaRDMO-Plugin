'''A portal item selected in a relation gets its page and is filled from the portal (#138).

The interview saves the relation through RDMO's API; MaRDMO's relation
handler adds the item's page and fills it, as when the item is selected on
its own page.  Here for benchmarks (algorithm catalog) and software
(workflow catalog); the portal's answers are given.
'''
import pytest

from MaRDMO.algorithm.models import Benchmark
from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_options
from MaRDMO.models import Software
from tests.db.conftest import select
from tests.db.test_relations import interview, page  # noqa: F401 (the interview fixture)

MIPLIB = ('mardi:Q6826034', 'MIPLIB 2017', 'mixed integer programming library')
LAPACK = ('mardi:Q6825400', 'LAPACK', 'linear algebra package')


@pytest.fixture
def filled(monkeypatch):
    '''The portal knows MIPLIB (a benchmark with its MORwiki ID) and LAPACK; returns the items filled.'''
    calls = []
    data = {MIPLIB[0]: Benchmark(reference={0: [get_options()['MORWIKI'], 'miplib2017']}), LAPACK[0]: Software()}

    def fetch(items, mardi_query, wikidata_query, entity):
        calls.append((entity.__name__, sorted(external_id for _, external_id, _ in items)))
        return {external_id: data[external_id] for _, external_id, _ in items if external_id in data}
    for module in ('MaRDMO.algorithm.handlers', 'MaRDMO.handler_base', 'MaRDMO.workflow.handlers'):
        monkeypatch.setattr(f'{module}._fetch_by_source', fetch)
    return calls


def reference(project, section, external_id):
    index = project.values.get(attribute__uri=f'{BASE_URI}domain/{section}/id', external_id=external_id).set_index
    return list(project.values.filter(attribute__uri=f'{BASE_URI}domain/{section}/reference',
                                      set_prefix=str(index)).values_list('text', flat=True))


def test_a_benchmark_selected_in_a_relation(interview, filled):  # noqa: F811
    documentation, post = interview('mardmo-algorithm-catalog')
    response = post('problem/benchmark-relatant', f'{MIPLIB[1]} ({MIPLIB[2]})', MIPLIB[0])
    assert response.status_code == 201
    assert page(documentation, 'benchmark', MIPLIB[0]) == (MIPLIB[1], MIPLIB[2])
    assert reference(documentation, 'benchmark', MIPLIB[0]) == ['miplib2017']
    assert filled == [('Benchmark', [MIPLIB[0]])]


def test_a_benchmark_selected_on_its_page(project, filled):
    documentation = project('mardmo-algorithm-catalog')
    select(documentation, 'algorithm', 'Benchmark', MIPLIB[0], f'{MIPLIB[1]} ({MIPLIB[2]})')
    assert page(documentation, 'benchmark', MIPLIB[0]) == (MIPLIB[1], MIPLIB[2])
    assert reference(documentation, 'benchmark', MIPLIB[0]) == ['miplib2017']


def test_a_benchmark_the_portal_does_not_know_keeps_its_name(interview, filled):  # noqa: F811
    documentation, post = interview('mardmo-algorithm-catalog')
    post('problem/benchmark-relatant', 'other benchmark (unknown to the portal)', 'mardi:Q1')
    assert page(documentation, 'benchmark', 'mardi:Q1') == ('other benchmark', 'unknown to the portal')
    assert reference(documentation, 'benchmark', 'mardi:Q1') == []


def test_software_selected_in_a_workflow_relation(interview, filled):  # noqa: F811
    documentation, post = interview('mardmo-interdisciplinary-workflow-catalog')
    post('algorithm/software-relatant', f'{LAPACK[1]} ({LAPACK[2]})', LAPACK[0])
    assert page(documentation, 'software', LAPACK[0]) == (LAPACK[1], LAPACK[2])
    assert ('Software', [LAPACK[0]]) in filled


def test_a_new_item_in_a_relation_is_not_looked_up(interview, filled):  # noqa: F811
    documentation, post = interview('mardmo-algorithm-catalog')
    response = post('problem/benchmark-relatant', 'my benchmark', 'not found')
    assert page(documentation, 'benchmark', response.json()['external_id']) == ('my benchmark', '')
    assert filled == []
