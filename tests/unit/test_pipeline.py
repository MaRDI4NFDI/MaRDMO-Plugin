'''MaRDMO.pipeline.run: what preview and export find before the export (#152).

The checks and the catalog's worker are stubs; what they raise decides.
'''
from types import SimpleNamespace

import pytest

from MaRDMO import pipeline
from MaRDMO.pages import PageRef
from MaRDMO.payload import DocumentationProblem, PortalUnavailable
from MaRDMO.problems import HEADER, Problem, report_lines
from MaRDMO.sources.http import EXPORT_CHECK_DEADLINE, EXPORT_RETRY_WAITS, check_deadline, check_waits

F4 = PageRef('formulation', 3, 'Navier-Stokes equation', 'F4')
PROJECT = SimpleNamespace(catalog='https://example.org/questions/mardmo-model-catalog')


class Checks:
    problems, unreachable = [], None

    def run_model(self, project, data, catalog):
        return list(Checks.problems)


def worker(raises=None, cyclic=False, seen=None):
    class Prepare:
        def export(self, answers, url):
            if seen is not None:
                seen.append((answers, check_waits(), check_deadline()))
            if raises:
                raise raises
            return ({'Item0000000001': {}, 'a': {'label': 'model a'}},
                    {'a': ['b'], 'b': ['a']} if cyclic else {'a': []})
    return Prepare


@pytest.fixture(autouse=True)
def checks(monkeypatch):
    Checks.problems, Checks.unreachable = [], None
    monkeypatch.setattr(pipeline, 'Checks', Checks)
    monkeypatch.setattr(pipeline, 'get_url', lambda *args: 'https://portal.example.org')


def run(prepare, **kwargs):
    return pipeline.run(PROJECT, {'formulation': {}}, prepare, 'run_model', **kwargs)


def test_problem_reads_as_the_checks_always_did():
    problem = Problem('Formula', F4, 'Missing Short Description')
    assert str(problem) == 'Formula (Page F4): Missing Short Description'
    assert str(Problem('Export', None, 'DOI: invalid')) == 'Export: DOI: invalid'
    assert report_lines([problem]) == [HEADER, 'Formula (Page F4): Missing Short Description']
    assert report_lines([]) == []


def test_clean_documentation_gives_the_payload():
    gate = run(worker())
    assert gate.clear and gate.payload == {'Item0000000001': {}, 'a': {'label': 'model a'}}
    assert gate.dependency == {'a': []}


def test_problems_of_the_checks_stop_before_the_export():
    seen = []
    Checks.problems = [Problem('Formula', F4, 'Missing Short Description')]
    gate = run(worker(seen=seen))
    assert not gate.clear and gate.payload is None and seen == []
    assert gate.groups == [('Formula', F4, ['Missing Short Description'])]


def test_problems_are_grouped_by_page_in_their_order():
    other = PageRef('formulation', 4, 'Euler equation', 'F5')
    Checks.problems = [Problem('Formula', F4, 'a'), Problem('Formula', F4, 'b'), Problem('Formula', other, 'c')]
    assert run(worker()).groups == [('Formula', F4, ['a', 'b']), ('Formula', other, ['c'])]


def test_problems_of_the_export_have_no_page():
    gate = run(worker(DocumentationProblem('"f", DOI: invalid', 'symbol a stands for Q1')))
    assert [str(problem) for problem in gate.problems] == ['Export: "f", DOI: invalid', 'Export: symbol a stands for Q1']
    assert not gate.internal and not gate.clear


def test_unreachable_portal():
    gate = run(worker(PortalUnavailable('Could not check which statements already exist')))
    assert gate.unreachable == 'Could not check which statements already exist' and not gate.problems
    assert not gate.clear


def test_unreachable_tex_check_stops_before_the_export():
    seen = []
    Checks.unreachable = 'The TeX check did not answer.'
    gate = run(worker(seen=seen))
    assert gate.unreachable == 'The TeX check did not answer.' and seen == []


@pytest.mark.parametrize('error', [ValueError('placeholder without item'), KeyError('community')])
def test_internal_error(error):
    gate = run(worker(error))
    assert gate.internal and len(gate.problems) == 1 and not gate.clear


def test_a_cycle_left_is_an_internal_error():
    '''The export breaks every cycle (#164): one left names its items and asks for a report.'''
    gate = run(worker(cyclic=True))
    assert gate.internal and not gate.clear
    assert [str(problem) for problem in gate.problems] == [
        'Export: The new items could not be put in an order of creation (model a -> b); nothing was exported, '
        'please report this to the MaRDMO developers']


def test_duplicates_stop_before_the_export():
    seen = []
    gate = run(worker(seen=seen), duplicates=SimpleNamespace(rows=[object()], failed=False))
    assert gate.duplicates and not gate.clear and seen == []


def test_failed_duplicate_lookup_is_unreachable():
    gate = run(worker(), duplicates=SimpleNamespace(rows=[], failed=True))
    assert gate.unreachable and not gate.clear


def test_the_preview_uses_its_limits_and_a_copy():
    seen = []
    answers = {'formulation': {0: {'Name': 'a'}}}
    pipeline.run(PROJECT, answers, worker(seen=seen), 'run_model', preview=True)
    exported, waits, deadline = seen[0]
    assert exported == answers and exported is not answers
    assert waits == pipeline.PREVIEW_RETRY_WAITS
    pipeline.run(PROJECT, answers, worker(seen=seen), 'run_model')
    assert seen[1][1] == EXPORT_RETRY_WAITS and seen[1][2] - deadline > EXPORT_CHECK_DEADLINE - pipeline.PREVIEW_DEADLINE - 5
