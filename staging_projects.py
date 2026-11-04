"""Round 1 of the staging cycle: projects with only new items, to be exported to staging by hand.

Every item is new (ID "not found", name and description typed in as in the
interview); the description of all items is the run label (default "MaRDMO
test 041126"), so the labels differ.  Three projects:

- model:     model A (problem, field, task, two formulas with symbols, three
             quantities, contains F1 as governing equation and F2 as initial
             condition, specialized by model B), publication by DOI
- algorithm: algorithm with algorithmic task, software (swMATH ID) and benchmark
- workflow:  workflow with model A and its task from staging (the interview
             offers only items of the MaRDI Portal there, so it is built after
             the model was exported: MODEL and TASK are their staging QIDs),
             process step with input and output data set and the algorithm on
             the software (ALGORITHM, SOFTWARE: staging QIDs from the algorithm
             project; new items if not given) and new hardware, with a parameter

MODE=CHECK (default): builds the projects as TEMP projects, runs MaRDMO's
checks on them, prints the messages and deletes them; nothing is fetched from
staging or the portal (the TeX check asks the portal as usual).
MODE=BUILD: builds them as projects "TEMP staging <kind>" that stay for the
export; needs MaRDMO configured for staging and STAGING=1.

In CHECK mode the publication lacks its name and description: they come
from the DOI lookup of the preview.

Environment: MODE, CASES (model,algorithm,workflow), RUN (description), OWNER (default marco),
MODEL, TASK, FIELD, ALGORITHM, SOFTWARE (staging QIDs for the workflow).
"""
import os, sys, time, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
from common import *  # noqa: F401,F403
from django.core.cache import cache
from MaRDMO.checks import Checks
from MaRDMO.main import MaRDMOExportProvider, _CATALOG_PREPARE_MAP
from preview_edits import answer, new_item, next_collection, own, MATHMODDB, MARDMO, OPTIONS, YES_NO_TEXT, DOI_OPTION

from django.contrib.auth.models import User
from rdmo.projects.models import Membership

MODE = os.environ.get('MODE', 'CHECK')
OWNER = os.environ.get('OWNER', 'marco')
RUN = os.environ.get('RUN', 'MaRDMO test 041126')
if MODE == 'BUILD' and get_url('mardi', 'uri') != STAGING:
    raise SystemExit('MODE=BUILD needs MaRDMO configured for staging (and STAGING=1); stopped.')


def item(name):
    """(label, description) of a test item."""
    return (f'MaRDMO test {name}', RUN)


def new(project, section, prefix, name):
    return new_item(project, section, prefix, *item(name))


def ref(name):
    """How a relation question stores the new test item *name*."""
    return own(*item(name))


def relation(project, path, option, prefix, block, relatants):
    """A relation block: relation type and its relatants."""
    answer(project, f'{path}-relation' if not path.endswith('/') else f'{path}relation', option=option,
           set_prefix=prefix, set_index=block)
    for line, name in enumerate(relatants):
        answer(project, f'{path}-relatant' if not path.endswith('/') else f'{path}relatant', signal=True,
               set_prefix=prefix, set_index=block, collection_index=line, **ref(name))


def build_model(p):
    field = new(p, 'field', 'AD', 'field')
    problem = new(p, 'problem', 'RP', 'problem')
    answer(p, 'problem/field-relatant', signal=True, set_prefix=str(problem), set_index=0, collection_index=0,
           **ref('field'))

    for name in ('quantity a', 'quantity b', 'quantity c'):
        q = new(p, 'quantity', 'QQK', name)
        answer(p, 'quantity/is-quantity-or-quantity-kind', option=f'{MATHMODDB}quantity', set_index=q)

    def formula(name, tex, elements):
        f = new(p, 'formulation', 'F', name)
        answer(p, 'formulation/formula', text=tex, set_prefix=f'{f}|0', set_index=0, collection_index=0)
        for j, (symbol, quantity) in enumerate(elements):
            answer(p, 'formulation/element/symbol', text=symbol, set_prefix=f'{f}|0|0', set_index=j)
            answer(p, 'formulation/element/quantity', signal=True, set_prefix=f'{f}|0|0', set_index=j,
                   **ref(quantity))
        return f

    formula('formula one', 'a = 2 b', [('a', 'quantity a'), ('b', 'quantity b')])
    formula('initial condition', 'a = 1', [('a', 'quantity a')])

    t = new(p, 'task', 'T', 'task')
    relation(p, 'task/formulation', f'{MATHMODDB}contains', f'{t}|0', 0, ['formula one'])
    relation(p, 'task/quantity', f'{MATHMODDB}contains-input', f'{t}|0', 0, ['quantity a'])
    relation(p, 'task/quantity', f'{MATHMODDB}contains-output', f'{t}|0', 1, ['quantity b'])

    m = new(p, 'model', 'X', 'model A')
    answer(p, 'model/problem-relatant', signal=True, set_prefix=str(m), set_index=0, collection_index=0,
           **ref('problem'))
    relation(p, 'model/formulation', f'{MATHMODDB}contains-governing-equation', f'{m}|0', 0, ['formula one'])
    relation(p, 'model/formulation', f'{MATHMODDB}contains-initial-condition', f'{m}|0', 1, ['initial condition'])
    answer(p, 'model/task-relatant', signal=True, set_prefix=str(m), set_index=0, collection_index=0,
           **ref('task'))
    relation(p, 'model/model', f'{MATHMODDB}specialized-by', str(m), 0, ['model B'])
    answer(p, 'model/model-assumption', signal=True, set_prefix=str(m), set_index=0, collection_index=0,
           **ref('initial condition'))

    b = new(p, 'model', 'X', 'model B')
    answer(p, 'model/problem-relatant', signal=True, set_prefix=str(b), set_index=0, collection_index=0,
           **ref('problem'))
    relation(p, 'model/formulation', f'{MATHMODDB}contains-governing-equation', f'{b}|0', 0, ['formula one'])

    k = next_collection(p, 'publication', '')
    answer(p, 'publication', text=f'P{k + 1}', set_index=k)
    answer(p, 'publication/id', signal=True, text='not found', external_id='not found', set_index=k)
    answer(p, 'publication/reference', option=DOI_OPTION, text='10.2113/gsecongeo.58.8.1246',
           set_index=k, collection_index=0)
    answer(p, 'publication/entity-relation', option=f'{MARDMO}documents', set_prefix=str(k), set_index=0)
    answer(p, 'publication/entity-relatant', signal=True, set_prefix=str(k), set_index=0, collection_index=0,
           **ref('model A'))
    return field


def build_algorithm(p):
    a = new(p, 'algorithm', 'X', 'algorithm')
    t = new(p, 'problem', 'AT', 'algorithmic task')
    s = new(p, 'software', 'S', 'software')
    b = new(p, 'benchmark', 'B', 'benchmark')
    answer(p, 'algorithm/problem-relatant', signal=True, set_prefix=str(a), set_index=0, collection_index=0,
           **ref('algorithmic task'))
    answer(p, 'algorithm/software-relatant', signal=True, set_prefix=str(a), set_index=0, collection_index=0,
           **ref('software'))
    answer(p, 'problem/benchmark-relatant', signal=True, set_prefix=str(t), set_index=0, collection_index=0,
           **ref('benchmark'))
    answer(p, 'software/reference', option=f'{OPTIONS}swmath', text='54321', set_prefix=str(s), set_index=0,
           collection_index=0)
    answer(p, 'software/benchmark-relatant', signal=True, set_prefix=str(s), set_index=0, collection_index=0,
           **ref('benchmark'))
    answer(p, 'benchmark/reference', option=f'{OPTIONS}morwiki', text='MaRDMO_Test_Benchmark',
           set_prefix=str(b), set_index=0, collection_index=0)


def staging(name, variable):
    """A staging item from the environment, stored as the interview stores a portal item."""
    qid = os.environ.get(variable)
    if not qid:
        return None
    for attempt in range(3):
        try:
            return {'text': labels('mardi', [qid])[qid], 'external_id': f'mardi:{qid}'}
        except ValueError:      # staging sometimes answers with an error page
            if attempt == 2:
                raise
            time.sleep(10)


def build_workflow(p):
    model, task, field = staging('model A', 'MODEL'), staging('task', 'TASK'), staging('field', 'FIELD')
    if not model or not task or not field:
        raise SystemExit('the workflow needs MODEL, TASK and FIELD (staging QIDs of model A, its task and field)')
    algorithm = staging('algorithm', 'ALGORITHM') or ref('workflow algorithm')
    software = staging('software', 'SOFTWARE') or ref('workflow software')
    w = new(p, 'workflow', 'X', 'workflow')
    answer(p, 'workflow/long-description', text='A workflow created to test MaRDMO exports on staging.',
           set_prefix=str(w), set_index=0, collection_index=0)
    answer(p, 'workflow/model', signal=True, set_prefix=f'{w}|0', set_index=0, **model)
    answer(p, 'workflow/task', signal=True, set_prefix=f'{w}|0', set_index=0, **task)
    for path in ('mathematical', 'runtime', 'result', 'original-platform', 'other-platform'):
        answer(p, f'workflow/reproducibility/{path}', option=f'{OPTIONS}yes_no/yes', set_prefix=f'{w}|0',
               set_index=0)
    answer(p, 'workflow/transferability', text='other test workflows', set_prefix=str(w), set_index=0,
           collection_index=0)
    answer(p, 'workflow/objective', text='test the export of MaRDMO to staging', set_prefix=str(w), set_index=0)

    for name, items in (('input data', '12'), ('output data', '3')):
        d = new(p, 'dataset', 'DS', name)
        for path, info in (('size', {'option': f'{OPTIONS}data-set-size/items', 'text': items}),
                           ('file-format', {'text': 'csv'}),
                           ('binary-or-text', {'option': f'{OPTIONS}binary-or-text/text'}),
                           ('proprietary', {'option': f'{OPTIONS}yes_no/no'}),
                           ('to-publish', {'option': f'{YES_NO_TEXT}no'}),
                           ('to-archive', {'option': f'{YES_NO_TEXT}no'})):
            answer(p, f'dataset/{path}', set_prefix=str(d), set_index=0, **info)

    if algorithm['external_id'] == 'not found':
        new(p, 'algorithm', 'A', 'workflow algorithm')
    if software['external_id'] == 'not found':
        new(p, 'software', 'S', 'workflow software')
    h = new(p, 'hardware', 'HW', 'workflow hardware')
    answer(p, 'hardware/nodes', text='1', set_prefix=str(h), set_index=0)
    answer(p, 'hardware/cores', text='4', set_prefix=f'{h}|0', set_index=0)
    answer(p, 'hardware/number-of-cpu', text='1', set_prefix=f'{h}|0', set_index=0)

    k = new(p, 'processstep', 'PS', 'process step')
    answer(p, 'processstep/input-data-set-relatant', signal=True, set_prefix=str(k), set_index=0,
           collection_index=0, **ref('input data'))
    answer(p, 'processstep/output-data-set-relatant', signal=True, set_prefix=str(k), set_index=0,
           collection_index=0, **ref('output data'))
    answer(p, 'processstep/algorithm-relatant', signal=True, set_prefix=f'{k}|0', set_index=0, collection_index=0,
           **algorithm)
    answer(p, 'processstep/software-relatant', signal=True, set_prefix=f'{k}|0', set_index=0, **software)
    answer(p, 'processstep/hardware-relatant', signal=True, set_prefix=f'{k}|0', set_index=0,
           **ref('workflow hardware'))
    answer(p, 'processstep/algorithm-parameter', text='tolerance = 0.1', set_prefix=f'{k}|0', set_index=0,
           collection_index=0)
    answer(p, 'processstep/software-documentation', option=f'{OPTIONS}url',
           text='https://example.org/mardmo-test-environment', set_prefix=f'{k}|0', set_index=0, collection_index=0)
    answer(p, 'processstep/field-relatant', signal=True, set_prefix=str(k), set_index=0, collection_index=0,
           **field)
    answer(p, 'workflow/step-relatant', signal=True, set_prefix=str(w), set_index=0, collection_index=0,
           **ref('process step'))


CASES = {'model': build_model, 'algorithm': build_algorithm, 'workflow': build_workflow}


def check(project):
    """MaRDMO's checks on the answers the export collects."""
    slug = project.catalog.uri.rsplit('/', 1)[1]
    cache.clear()
    provider = MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, _ = provider.get_post_data()
    _, _, check_method = _CATALOG_PREPARE_MAP[slug]
    return [str(e) for e in getattr(Checks(), check_method)(
        project=project, data=answers, catalog=str(project.catalog)) or []]


if __name__ in ('__main__', 'django.core.management.commands.shell'):
    cases = os.environ.get('CASES', ','.join(CASES)).split(',')
    title = 'TEMP staging check' if MODE == 'CHECK' else None
    try:
        for case in cases:
            _, slug, _, _ = TYPES[case]
            name = title or f'TEMP staging {case}'
            Project.objects.filter(title=name).delete()
            p = new_project(slug, name)
            try:
                CASES[case](p)
                messages = check(p)
                print(f'{case}: {len(messages)} check messages', flush=True)
                for message in messages:
                    print('   ', message)
                if MODE == 'BUILD':
                    # the user exports it: owner, so it is listed under "My Projects"
                    Membership.objects.create(project=p, user=User.objects.get(username=OWNER), role='owner')
                    print(f'   project "{name}" (id {p.id}) ready for the export')
            except Exception:
                print(case, 'ERROR', traceback.format_exc())
            finally:
                if MODE == 'CHECK':
                    p.delete()
    finally:
        Project.objects.filter(title='TEMP staging check').delete()
