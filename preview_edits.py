"""Preview against payload for projects with new content, as a user would enter it.

A portal item is filled as usual, then typical interview entries are added:
new items of the user's own (ID "not found", name and description typed in),
formulas with elements, relations with roles and assumptions, aliases,
detailed descriptions and a publication by DOI.  Every answer is saved and
the interview's signal sent, so MaRDMO's handlers run as in the interview.
Preview and payload are then saved like preview_payload.py does (nothing is
posted) and compared with preview_compare.py.

Environment: CASES (comma-separated, default all: model), OUT (default
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


CASES = {'model': ('Q6775746', 'model', edit_model)}

if __name__ in ('__main__', 'django.core.management.commands.shell'):
    cases = os.environ.get('CASES', ','.join(CASES)).split(',')
    TEXTS.update(labels('mardi', ['Q6775415', 'Q6675318', 'Q6775746']))
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
