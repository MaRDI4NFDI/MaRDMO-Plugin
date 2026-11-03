"""Preview against payload for projects with new content, as a user would enter it.

A portal item is filled as usual, then typical interview entries are added:
new items of the user's own (ID "not found", name and description typed in),
formulas with elements, relations with roles and assumptions, aliases,
detailed descriptions and a publication by DOI.  Every answer is saved and
the interview's signal sent, so MaRDMO's handlers run as in the interview.
Preview and payload are then saved like preview_payload.py does (nothing is
posted) and compared with preview_compare.py.

Environment: CASES (comma-separated, default all: model, algorithm, workflow), OUT (default
results/preview-edited).
"""
import datetime, json, os, sys, time, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
os.environ['OUT'] = os.environ.get('OUT') or os.path.join(
    os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')), 'results', 'preview-edited')
from common import *  # noqa: F401,F403
from preview_payload import preview_and_payload, out

TITLE = 'TEMP preview edited'
MATHMODDB = 'https://rdmo.mardi4nfdi.de/terms/options/mathmoddb/'
MARDMO = 'https://rdmo.mardi4nfdi.de/terms/options/mardmo/'
DOI_OPTION = 'https://rdmo.mardi4nfdi.de/terms/options/doi'


def answer(project, path, signal=False, **info):
    """Save one answer; with signal, send what the interview sends after selecting an item."""
    value, created = value_editor(project=project, uri=f'{BASE_URI}domain/{path}', info=info)
    if signal:
        (value_created if created else value_updated).send(sender=Value, instance=value)
        time.sleep(PAUSE)
    return value


def next_set(project, section):
    """Next free set index (tab) of a section."""
    return max(project.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/{section}', set_prefix='')
               .values_list('set_index', flat=True), default=-1) + 1


def new_item(project, section, prefix, name, description):
    """A tab with an item of the user's own: ID "not found", name and description typed in."""
    k = next_set(project, section)
    answer(project, section, text=f'{prefix}{k + 1}', set_index=k)
    answer(project, f'{section}/id', signal=True, text='not found', external_id='not found', set_index=k)
    answer(project, f'{section}/name', text=name, set_prefix=str(k), set_index=0)
    answer(project, f'{section}/description', text=description, set_prefix=str(k), set_index=0)
    return k


def own(name, description):
    """How a relation question stores an item of the user's own."""
    return {'text': f'{name} ({description})', 'external_id': 'not found'}


def portal(qid):
    """How a relation question stores a portal item."""
    return {'text': TEXTS[qid], 'external_id': f'mardi:{qid}'}


TEXTS = {}


def edit_model(p):
    """Kriging model: new quantity and formula, relations with role and assumption, alias, publication."""
    edits = []
    weight = ('Kriging weight', 'weight of an observation in the Kriging predictor')
    predictor = ('Kriging predictor', 'best linear unbiased predictor of the Kriging model')

    q = new_item(p, 'quantity', 'QQK', *weight)
    answer(p, 'quantity/is-quantity-or-quantity-kind', option=f'{MATHMODDB}quantity', set_index=q)
    edits.append(f'new quantity QQK{q + 1} {weight[0]} (class quantity)')

    f = new_item(p, 'formulation', 'F', *predictor)
    answer(p, 'formulation/formula', text=r'\hat{Z}(x_0) = \sum_{i=1}^{n} \lambda_i Z(x_i)',
           set_prefix=f'{f}|0', set_index=0, collection_index=0)
    for j, (symbol, item) in enumerate(((r'\hat{Z}(x_0)', portal('Q6775415')), (r'\lambda_i', own(*weight)),
                                        (r'Z(x_i)', portal('Q6775415')))):
        answer(p, 'formulation/element/symbol', text=symbol, set_prefix=f'{f}|0|0', set_index=j)
        answer(p, 'formulation/element/quantity', signal=True, set_prefix=f'{f}|0|0', set_index=j, **item)
    edits.append(f'new formula F{f + 1} {predictor[0]} with defining formula and 3 elements (one new quantity)')

    # model contains the new formula as governing equation (new relation set)
    answer(p, 'model/formulation-relation', option=f'{MATHMODDB}contains-governing-equation',
           set_prefix='0|0', set_index=1)
    answer(p, 'model/formulation-relatant', signal=True, set_prefix='0|0', set_index=1, collection_index=0,
           **own(*predictor))
    edits.append('model contains governing equation: new formula')

    # assumption for the existing specialization (model specialized by simple Kriging)
    answer(p, 'model/model-assumption', signal=True, set_prefix='0', set_index=0, collection_index=0,
           **own(*predictor))
    edits.append('assumption (new formula) on the existing "specialized by" relation')

    # new model relation: similar to another portal model
    answer(p, 'model/model-relation', option=f'{MATHMODDB}similar-to', set_prefix='0', set_index=1)
    answer(p, 'model/model-relatant', signal=True, set_prefix='0', set_index=1, collection_index=0,
           **portal('Q6675318'))
    edits.append('model similar to Q6675318')

    answer(p, 'model/alias', text='ordinary Kriging model', set_prefix='0', set_index=0, collection_index=0)
    answer(p, 'model/long-description', text='Kriging predicts values at unobserved locations as weighted '
           'sums of observations, with weights from the covariance structure.',
           set_prefix='0', set_index=0, collection_index=0)
    edits.append('alias and detailed description of the model')

    # publication by DOI, documenting the model
    k = next_set(p, 'publication')
    answer(p, 'publication', text=f'P{k + 1}', set_index=k)
    answer(p, 'publication/id', signal=True, text='not found', external_id='not found', set_index=k)
    answer(p, 'publication/reference', option=DOI_OPTION, text='10.2113/gsecongeo.58.8.1246',
           set_index=k, collection_index=0)
    answer(p, 'publication/entity-relation', option=f'{MARDMO}documents', set_prefix=str(k), set_index=0)
    answer(p, 'publication/entity-relatant', signal=True, set_prefix=str(k), set_index=0, collection_index=0,
           **portal('Q6775746'))
    edits.append(f'publication P{k + 1} by DOI 10.2113/gsecongeo.58.8.1246, documents the model')
    return edits


MATHALGODB = 'https://rdmo.mardi4nfdi.de/terms/options/mathalgodb/'
OPTIONS = 'https://rdmo.mardi4nfdi.de/terms/options/'
YES_NO_TEXT = 'https://rdmorganiser.github.io/terms/options/yes_with_text_no/'


def next_collection(project, path, prefix):
    """Next free collection index (line) of a question in a tab."""
    return max(project.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/{path}', set_prefix=prefix)
               .values_list('collection_index', flat=True), default=-1) + 1


def edit_algorithm(p):
    """Algorithm Q6825339: new software and benchmark with references, their relations, a subclass relation."""
    edits = []
    software = ('TestSolver', 'test implementation of the algorithm')
    benchmark = ('Test benchmark set', 'benchmark problems for the test implementation')

    s = new_item(p, 'software', 'S', *software)
    answer(p, 'software/reference', option=f'{OPTIONS}swmath', text='54321', set_prefix=str(s), set_index=0,
           collection_index=0)
    answer(p, 'software/reference', option=f'{OPTIONS}source-code-repository-url', text='https://example.org/testsolver',
           set_prefix=str(s), set_index=0, collection_index=1)
    answer(p, 'software/programming-language-relatant', signal=True, set_prefix=str(s), set_index=0,
           collection_index=0, **portal('Q6230810'))
    edits.append(f'new software S{s + 1} {software[0]} with swMATH ID, source code URL, programming language Python')

    b = new_item(p, 'benchmark', 'B', *benchmark)
    answer(p, 'benchmark/reference', option=f'{OPTIONS}morwiki', text='Test_Benchmark', set_prefix=str(b),
           set_index=0, collection_index=0)
    edits.append(f'new benchmark B{b + 1} {benchmark[0]} with MORwiki ID')

    answer(p, 'algorithm/software-relatant', signal=True, set_prefix='0', set_index=0,
           collection_index=next_collection(p, 'algorithm/software-relatant', '0'), **own(*software))
    answer(p, 'problem/benchmark-relatant', signal=True, set_prefix='0', set_index=0,
           collection_index=next_collection(p, 'problem/benchmark-relatant', '0'), **own(*benchmark))
    answer(p, 'software/benchmark-relatant', signal=True, set_prefix=str(s), set_index=0, collection_index=0,
           **own(*benchmark))
    edits.append('algorithm implemented by the new software, task instantiated by the new benchmark, '
                 'software tests the benchmark')

    k = max(p.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/algorithm/algorithm-relation',
                            set_prefix='0').values_list('set_index', flat=True), default=-1) + 1
    answer(p, 'algorithm/algorithm-relation', option=f'{MATHALGODB}subclass-of', set_prefix='0', set_index=k)
    answer(p, 'algorithm/algorithm-relatant', signal=True, set_prefix='0', set_index=k, collection_index=0,
           **portal('Q6825578'))
    edits.append('algorithm subclass of Q6825578')
    return edits


def edit_workflow(p):
    """Workflow Q6032641: new data set with all fields, new process step with data and an algorithm usage."""
    edits = []
    data = ('Validated rule set', 'logical rules checked against held-out objects')
    step = ('Validate logical rules', 'checks the extracted rules against held-out objects')

    d = new_item(p, 'dataset', 'DS', *data)
    for path, info in (('size', {'option': f'{OPTIONS}data-set-size/items', 'text': '42'}),
                       ('file-format', {'text': 'csv'}),
                       ('binary-or-text', {'option': f'{OPTIONS}binary-or-text/text'}),
                       ('proprietary', {'option': f'{OPTIONS}yes_no/no'}),
                       ('to-publish', {'option': f'{YES_NO_TEXT}yes', 'text': '10.5281/zenodo.1234567'}),
                       ('to-archive', {'option': f'{YES_NO_TEXT}yes', 'text': '2035'})):
        answer(p, f'dataset/{path}', set_prefix=str(d), set_index=0, **info)
    edits.append(f'new data set DS{d + 1} {data[0]}: 42 items, csv, text, open, published (DOI), archived until 2035')

    k = new_item(p, 'processstep', 'PS', *step)
    answer(p, 'processstep/input-data-set-relatant', signal=True, set_prefix=str(k), set_index=0, collection_index=0,
           **portal('Q6486606'))
    answer(p, 'processstep/output-data-set-relatant', signal=True, set_prefix=str(k), set_index=0, collection_index=0,
           **own(*data))
    answer(p, 'processstep/algorithm-relatant', signal=True, set_prefix=f'{k}|0', set_index=0, collection_index=0,
           **portal('Q6032636'))
    answer(p, 'processstep/software-relatant', signal=True, set_prefix=f'{k}|0', set_index=0, **portal('Q6230812'))
    answer(p, 'processstep/algorithm-parameter', text='threshold = 0.5', set_prefix=f'{k}|0', set_index=0,
           collection_index=0)
    edits.append(f'new process step PS{k + 1} {step[0]}: input Q6486606, output the new data set, '
                 'uses RAP Algorithm on Jupyter Notebook with a parameter')

    answer(p, 'workflow/step-relatant', signal=True, set_prefix='0', set_index=0,
           collection_index=next_collection(p, 'workflow/step-relatant', '0'), **own(*step))
    edits.append('workflow contains the new process step')
    return edits


CASES = {'model': ('Q6775746', 'model', edit_model),
         'algorithm': ('Q6825339', 'algorithm', edit_algorithm),
         'workflow': ('Q6032641', 'workflow', edit_workflow)}

if __name__ in ('__main__', 'django.core.management.commands.shell'):
    cases = os.environ.get('CASES', ','.join(CASES)).split(',')
    TEXTS.update(labels('mardi', ['Q6775415', 'Q6675318', 'Q6775746', 'Q6230810', 'Q6825578',
                                  'Q6486606', 'Q6032636', 'Q6230812']))
    try:
        for case in cases:
            qid, kind, edit = CASES[case]
            source, slug, qkey, item_type = TYPES[kind]
            res = {'qid': f'{case}-{qid}', 'source': source, 'time': str(datetime.datetime.now())}
            html = ''
            try:
                p = new_project(slug, TITLE)
                TEXTS.update(labels(source, [qid]))
                select(p, qkey, item_type, f'{source}:{qid}', TEXTS[qid], 0)
                res['edits'] = edit(p)
                res['values'] = dump(p)
                html = preview_and_payload(p, res)
            except Exception:
                res['error'] = traceback.format_exc()
            finally:
                Project.objects.filter(title=TITLE).delete()
            open(os.path.join(out, f"{res['qid']}.html"), 'w').write(html)
            json.dump(res, open(os.path.join(out, f"{res['qid']}.json"), 'w'), indent=1, default=str)
            print(f"{case}: {len(res.get('edits', []))} edits, preview {len(html)} chars, "
                  f"payload {len(res['payload']) if 'payload' in res else '-'}"
                  f"{'  export: ' + res['export message'][0][:150] if 'export message' in res else ''}"
                  f"{'  EXPORT CRASH ' + res['export crash'].strip().splitlines()[-1] if 'export crash' in res else ''}"
                  f"{'  ERROR ' + res['error'].strip().splitlines()[-1] if 'error' in res else ''}", flush=True)
    finally:
        Project.objects.filter(title=TITLE).delete()
        print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
