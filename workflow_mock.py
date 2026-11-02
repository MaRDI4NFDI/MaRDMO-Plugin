"""Workflow filling with mock process step usages.

The portal has one MaRDMO workflow (Q6032641) with a single algorithm usage,
so the real process step data is extended here: after the real (read-only)
query, mock algorithm and method usages with software, hardware, instrument,
parameters and documentation are added to the process steps.  The mock items
are real portal items, so the cascade into the Algorithm and Software
sections runs as usual.

Cases:

- twice:   fill the workflow, select it again -> values identical
- gained:  the portal "gains" a usage for a process step that already has two,
           the step is selected again -> every usage set holds exactly one usage
- manual:  one usage set is deleted by hand, the step is selected again -> the
           usage comes back, no set mixes two usages
- order:   three process steps selected A, B, C and C, B, A -> same content
- twin:    one algorithm used with two different software in one step
           (reported only: shows what MaRDMO writes)

"Usage sets" are checked by reading every (set_prefix, set_index) of the
process step's algorithm and method questions back into
(relatant, platform, hardware, parameters, documentation) and comparing them
with the usages the handler received.

Environment: OUT (default results/workflow-mock-<date>).
"""
import collections, datetime, json, os, sys, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
from common import *  # noqa: F401,F403
import MaRDMO
import MaRDMO.workflow.handlers as workflow_handlers
from MaRDMO.helpers import extract_parts
from MaRDMO.workflow.models import ProcessStep, ProcessStepUsage

TITLE = 'TEMP workflow mock'
SLUG = 'mardmo-interdisciplinary-workflow-catalog'
WORKFLOW = 'mardi:Q6032641'
STEP_A, STEP_B, STEP_C = 'mardi:Q6486604', 'mardi:Q6486607', 'mardi:Q6486610'   # C has the real RAP usage
SOFTWARE, HARDWARE = 'mardi:Q6230812', 'mardi:Q6487066'                       # Jupyter Notebook, Lenovo IdeaPad
ALG_1, ALG_2, ALG_3 = 'mardi:Q6825514', 'mardi:Q7401727', 'mardi:Q7401075'
DATA_1, DATA_2, DATA_3 = 'mardi:Q6486605', 'mardi:Q6486606', 'mardi:Q6486608'
out_base = os.environ.get('OUT') or os.path.join(HERE, 'results', f'workflow-mock-{datetime.date.today()}')
os.makedirs(os.path.dirname(out_base), exist_ok=True)
print('code from', MaRDMO.__file__)

TEXT = labels('mardi', [q.split(':')[1] for q in (WORKFLOW, STEP_A, STEP_B, STEP_C, SOFTWARE, HARDWARE, ALG_1, ALG_2, ALG_3, DATA_1, DATA_2, DATA_3)])
TEXT = {f'mardi:{k}': v for k, v in TEXT.items()}


def parts(item):
    """(item, label, description) with the real label and description, as the query returns them."""
    label, description, _ = extract_parts(TEXT[item])
    return [item, label, description]


def usage(item, platform=None, hardware=None, doi='', url='', params=()):
    """Raw usage string as the process step query returns it."""
    raw = ' || '.join(parts(item) + (parts(platform) if platform else ['', '', ''])
                      + (parts(hardware) if hardware else ['', '', '']) + [doi, url])
    return raw + (' >|< ' + ' || '.join(params) if params else '')


ALG = {
    'a1': usage(ALG_1, SOFTWARE, HARDWARE, doi='10.1000/mock.1', params=('tolerance = 1e-6', 'max iterations = 100')),
    'a2': usage(ALG_2, SOFTWARE, url='https://example.org/mock-2', params=('order = 2',)),
    'a3': usage(ALG_3, SOFTWARE, HARDWARE, doi='10.1000/mock.3', url='https://example.org/mock-3', params=('new = 1',)),
    'a1-other-sw': usage(ALG_1, HARDWARE, params=('other platform',)),
}
# methods and instruments are not followed into other sections, so any items do
MET = {
    'm1': usage(DATA_1, DATA_2, doi='10.1000/mock.m1', params=('temperature = 20 C',)),
    'm2': usage(DATA_3, url='https://example.org/mock-m2'),
}
SCENARIOS = {
    'base':   {STEP_A: (['a1', 'a2'], ['m1']), STEP_B: ([], ['m1', 'm2']), STEP_C: (['a1'], [])},
    'gained': {STEP_A: (['a1', 'a2', 'a3'], ['m1']), STEP_B: ([], ['m1', 'm2']), STEP_C: (['a1'], [])},
    'twin':   {STEP_A: (['a1', 'a1-other-sw'], [])},
}
state = {'scenario': 'base'}
received = {}   # process step -> ProcessStep the handler got last

_real_fetch = workflow_handlers._fetch_by_source


def _mock_fetch(items, mardi_file, wikidata_file, model_class):
    data = _real_fetch(items, mardi_file, wikidata_file, model_class)
    if model_class is ProcessStep:
        for external_id, step in data.items():
            algs, mets = SCENARIOS[state['scenario']].get(external_id, ([], []))
            step.uses_algorithm += [ProcessStepUsage.from_query(ALG[k]) for k in algs]
            step.uses_method += [ProcessStepUsage.from_query(MET[k]) for k in mets]
            received[external_id] = step
    return data


workflow_handlers._fetch_by_source = _mock_fetch

USAGE_ATTRS = {
    'algorithm': ('algorithm-relatant', 'software-relatant', 'hardware-relatant', 'algorithm-parameter', 'software-documentation'),
    'method':    ('method-relatant', 'instrument-relatant', 'hardware-relatant', 'method-parameter', 'method-documentation'),
}


def expected_usages(step):
    def one(u):
        docs = tuple(sorted(d[1] for d in (u.doi, u.url) if d))
        return (u.id, u.qualifier or '', u.hardware or '', tuple((u.parameters or '').split(' || ')) if u.parameters else (), docs)
    return {'algorithm': sorted(one(u) for u in step.uses_algorithm), 'method': sorted(one(u) for u in step.uses_method)}


def written_usages(values, step_index):
    """Read the usage sets of one process step back into usage tuples."""
    prefix = f'{step_index}|0'
    found = {}
    for kind, (rel, plat, hw, par, doc) in USAGE_ATTRS.items():
        sets = collections.defaultdict(lambda: collections.defaultdict(list))
        for attr, pre, sidx, cidx, text, ext, _ in values:
            short = attr.rsplit('/', 1)[1]
            if pre == prefix and (short in (rel, plat, par, doc) or short == hw and kind == 'algorithm'):
                sets[sidx][short].append((cidx, ext or text))
        rows = []
        for sidx, attrs in sorted(sets.items()):
            if not attrs.get(rel):
                rows.append(('SET WITHOUT RELATANT', sidx, dict(attrs)))
                continue
            if len(attrs[rel]) > 1 or len(attrs.get(plat, [])) > 1 or len(attrs.get(hw, [])) > 1:
                rows.append(('MIXED SET', sidx, dict(attrs)))
                continue
            rows.append((attrs[rel][0][1], (attrs.get(plat) or [(0, '')])[0][1], (attrs.get(hw) or [(0, '')])[0][1],
                         tuple(t for _, t in sorted(attrs.get(par, []))), tuple(sorted(t for _, t in attrs.get(doc, [])))))
        found[kind] = sorted(rows, key=str)
    return found


def step_index(project, external_id):
    return Value.objects.get(project=project, snapshot=None, set_prefix='', external_id=external_id,
                             attribute__uri=f'{BASE_URI}domain/processstep/id').set_index


def check_steps(project, values):
    """Compare every mocked process step's usage sets with what the handler received."""
    report = {}
    for external_id in (STEP_A, STEP_B, STEP_C):
        if external_id not in received:
            continue
        try:
            idx = step_index(project, external_id)
        except Value.DoesNotExist:
            continue
        want, got = expected_usages(received[external_id]), written_usages(values, idx)
        same = all(sorted(want[k], key=str) == got[k] for k in want)
        report[external_id] = 'ok' if same else {'expected': want, 'written': got}
    return report


def ok(report):
    return all(v == 'ok' for v in report.values())


def show(case, result):
    short = result if isinstance(result, str) else result.get('result', 'see json')
    print(f'{case:8} {short}')


# the cases run only when the script is run; preview_payload.py imports the mock (MOCK=1)
if __name__ in ('__main__', 'django.core.management.commands.shell'):
    results = {'started': str(datetime.datetime.now())}
    try:
        # twice
        p = new_project(SLUG, TITLE)
        select(p, 'workflow', 'Workflow', WORKFLOW, TEXT[WORKFLOW], 0)
        first = dump(p)
        steps = check_steps(p, first)
        select(p, 'workflow', 'Workflow', WORKFLOW, TEXT[WORKFLOW], 0, again=True)
        second = dump(p)
        results['twice'] = {'values': len(first), 'usage sets': steps,
                            'result': ('identical' if first == second else 'DIFFERENT')
                                      + (', usage sets ok' if ok(steps) else ', USAGE SETS WRONG'),
                            'gaps': gaps(first)}
        if first != second:
            results['twice']['diff'] = diff(collections.Counter(first), collections.Counter(second))
        show('twice', results['twice'])

        # gained
        state['scenario'] = 'gained'
        reselect(p, Value.objects.get(project=p, snapshot=None, set_prefix='', external_id=STEP_A,
                                      attribute__uri=f'{BASE_URI}domain/processstep/id'))
        third = dump(p)
        steps = check_steps(p, third)
        results['gained'] = {'usage sets': steps, 'result': 'usage sets ok' if ok(steps) else 'USAGE SETS WRONG'}
        show('gained', results['gained'])
        Project.objects.filter(title=TITLE).delete()

        # manual
        state['scenario'] = 'base'
        p = new_project(SLUG, TITLE)
        select(p, 'workflow', 'Workflow', WORKFLOW, TEXT[WORKFLOW], 0)
        before = dump(p)
        idx = step_index(p, STEP_A)
        alg_attrs = [f'{BASE_URI}domain/processstep/{a}' for a in USAGE_ATTRS['algorithm']]
        first_set = min(v[2] for v in before if v[1] == f'{idx}|0' and v[0].endswith('/algorithm-relatant'))
        deleted = Value.objects.filter(project=p, snapshot=None, set_prefix=f'{idx}|0', set_index=first_set,
                                       attribute__uri__in=alg_attrs).delete()[0]
        reselect(p, Value.objects.get(project=p, snapshot=None, set_prefix='', set_index=idx,
                                      attribute__uri=f'{BASE_URI}domain/processstep/id'))
        after = dump(p)
        steps = check_steps(p, after)
        results['manual'] = {'deleted values': deleted, 'usage sets': steps,
                             'result': ('usage sets ok' if ok(steps) else 'USAGE SETS WRONG')
                                       + (', same content' if content(after, True) == content(before, True) else ', CONTENT DIFFERS')}
        show('manual', results['manual'])
        Project.objects.filter(title=TITLE).delete()

        # order
        dumps = []
        for order in ((STEP_A, STEP_B, STEP_C), (STEP_C, STEP_B, STEP_A)):
            p = new_project(SLUG, TITLE)
            for i, step in enumerate(order):
                select(p, 'workflow', 'Process Step', step, TEXT[step], i)
            values = dump(p)
            dumps.append((values, check_steps(p, values)))
            p.delete()
        (a, sa), (b, sb) = dumps
        results['order'] = {'usage sets': [sa, sb], 'gaps': [gaps(a), gaps(b)]}
        if content(a) == content(b):
            results['order']['result'] = 'same content'
        elif content(a, True) == content(b, True):
            results['order']['result'] = 'same values, other inner numbers'
            results['order']['renumbered'] = sorted({k[0] for k in (content(a) - content(b)) + (content(b) - content(a))})
        else:
            results['order']['result'] = 'DIFF'
            results['order']['loose'] = diff(content(a, True), content(b, True))
        results['order']['result'] += ', usage sets ok' if ok(sa) and ok(sb) else ', USAGE SETS WRONG'
        show('order', results['order'])

        # twin
        state['scenario'] = 'twin'
        p = new_project(SLUG, TITLE)
        select(p, 'workflow', 'Process Step', STEP_A, TEXT[STEP_A], 0)
        results['twin'] = {'written': written_usages(dump(p), 0)['algorithm']}
        results['twin']['result'] = f"{len(results['twin']['written'])} of 2 usages written"
        show('twin', results['twin'])
    except Exception:
        results['error'] = traceback.format_exc()
        print(results['error'])
    finally:
        workflow_handlers._fetch_by_source = _real_fetch
        Project.objects.filter(title=TITLE).delete()
        results['finished'] = str(datetime.datetime.now())
        json.dump(results, open(out_base + '.json', 'w'), indent=1, default=str)
        print('\nresults:', out_base + '.json')
        print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
