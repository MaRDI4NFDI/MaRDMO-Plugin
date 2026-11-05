"""Round 2 of the staging cycle: change the items of round 1 as a user would, export by hand.

Each project fills a staging item (selected as in the interview), changes
it, and is checked with a dry run (preview, checks and payload against
staging; nothing is posted) before it is kept for the export.  Before round
2, two statements were changed by hand on staging: symbol b of formula one
lost "symbol represents", and "model A contains initial condition" got a
second role (boundary condition).

Cases (one export each, in this order; later ones need earlier exports):

  symbol     model A; b of formula one gets quantity b again
             -> b is completed (partial); the statement with two roles
                and everything else stays (an unchanged import)
  relations  model A; plain "contains initial condition", and formula one
             as second assumption of "specialized by model B"
             -> one new statement, one partial
  conflict   model A; symbol a of formula one gets quantity c
             -> the export stops (a stands for quantity a on staging)
  workflow   the workflow; the process step uses the algorithm also on a
             new software (and the hardware), and the existing usage gets
             a second parameter -> one new statement, one partial

Needs MaRDMO configured for staging and STAGING=1.  Environment: CASES,
OWNER (default marco), DRY=1 (dry run only: the project is deleted).
"""
import json, os, sys, time, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
os.environ['OUT'] = os.environ.get('OUT') or os.path.join(
    os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')), 'results', 'staging-round2')
from common import *  # noqa: F401,F403
from django.contrib.auth.models import User
from rdmo.projects.models import Membership
from preview_edits import answer, new_item, next_collection, MATHMODDB, OPTIONS
from preview_payload import preview_and_payload, out
from MaRDMO.getters import get_properties

if get_url('mardi', 'uri') != STAGING:
    raise SystemExit('round 2 needs MaRDMO configured for staging (and STAGING=1); stopped.')

OWNER = os.environ.get('OWNER', 'marco')
RUN = 'MaRDMO test 041126'
QID = {'model A': 'Q21993', 'model B': 'Q21991', 'formula one': 'Q21989', 'initial condition': 'Q21988',
       'quantity a': 'Q21983', 'quantity b': 'Q21984', 'quantity c': 'Q21985', 'workflow': 'Q22005',
       'process step': 'Q22004', 'algorithm': 'Q21997', 'hardware': 'Q22003'}
TEXT = {}


def staging_item(name):
    """How the interview stores a staging item: label (description) [mardi]."""
    qid = QID[name]
    if qid not in TEXT:
        for attempt in range(6):
            try:
                TEXT.update(labels('mardi', [qid]))
                break
            except ValueError:      # staging answers with an error page at times
                if attempt == 5:
                    raise
                time.sleep(20)
    return {'text': TEXT[qid], 'external_id': f'mardi:{qid}'}


def page(project, section, name):
    """Set index of the page (tab) of a staging item."""
    return project.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/{section}/id',
                              external_id=f'mardi:{QID[name]}').set_index


def element(project, formula_page, symbol):
    """Set index of the symbol table row of *symbol*."""
    return project.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/formulation/element/symbol',
                              set_prefix=f'{formula_page}|0|0', text=symbol).set_index


def block(project, path, prefix):
    """Next free relation block of a relation question."""
    return max(project.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/{path}', set_prefix=prefix)
               .values_list('set_index', flat=True), default=-1) + 1


def symbol(p):
    f = page(p, 'formulation', 'formula one')
    answer(p, 'formulation/element/quantity', signal=True, set_prefix=f'{f}|0|0',
           set_index=element(p, f, 'b'), **staging_item('quantity b'))


def relations(p):
    m = page(p, 'model', 'model A')
    k = block(p, 'model/formulation-relation', f'{m}|0')
    answer(p, 'model/formulation-relation', option=f'{MATHMODDB}contains', set_prefix=f'{m}|0', set_index=k)
    answer(p, 'model/formulation-relatant', signal=True, set_prefix=f'{m}|0', set_index=k, collection_index=0,
           **staging_item('initial condition'))
    specialization = p.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/model/model-relatant',
                                  set_prefix=str(m), external_id=f'mardi:{QID["model B"]}').set_index
    answer(p, 'model/model-assumption', signal=True, set_prefix=str(m), set_index=specialization,
           collection_index=next_collection(p, 'model/model-assumption', str(m)), **staging_item('formula one'))


def conflict(p):
    f = page(p, 'formulation', 'formula one')
    answer(p, 'formulation/element/quantity', signal=True, set_prefix=f'{f}|0|0',
           set_index=element(p, f, 'a'), **staging_item('quantity c'))


def workflow(p):
    s = new_item(p, 'software', 'S', 'MaRDMO test second software', RUN)
    answer(p, 'software/reference', option=f'{OPTIONS}swmath', text='54322', set_prefix=str(s), set_index=0,
           collection_index=0)
    k = page(p, 'processstep', 'process step')
    usage = p.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/processstep/algorithm-relatant',
                         set_prefix=f'{k}|0', external_id=f'mardi:{QID["algorithm"]}').set_index
    answer(p, 'processstep/algorithm-parameter', text='step size = 0.01', set_prefix=f'{k}|0', set_index=usage,
           collection_index=next_collection(p, 'processstep/algorithm-parameter', f'{k}|0'))
    n = block(p, 'processstep/algorithm-relatant', f'{k}|0')
    answer(p, 'processstep/algorithm-relatant', signal=True, set_prefix=f'{k}|0', set_index=n, collection_index=0,
           **staging_item('algorithm'))
    answer(p, 'processstep/software-relatant', signal=True, set_prefix=f'{k}|0', set_index=n,
           text=f'MaRDMO test second software ({RUN})', external_id='not found')
    answer(p, 'processstep/hardware-relatant', signal=True, set_prefix=f'{k}|0', set_index=n,
           **staging_item('hardware'))
    answer(p, 'processstep/software-documentation', option=f'{OPTIONS}url',
           text='https://example.org/mardmo-test-environment-2', set_prefix=f'{k}|0', set_index=n, collection_index=0)


CASES = {'symbol': ('model', 'model A', symbol), 'relations': ('model', 'model A', relations),
         'conflict': ('model', 'model A', conflict), 'workflow': ('workflow', 'workflow', workflow)}


def report(res):
    """What the export would do: messages, and every statement not on staging yet."""
    pname = {v: k for k, v in get_properties().items()}
    print('   checks:', [m for m in res.get('messages', []) if 'prevented' not in m] or 'none')
    if 'export message' in res:
        print('   export stops:', res['export message'])
    payload = res.get('payload') or {}
    items = {k: e for k, e in payload.items() if k.startswith('Item')}
    ident = lambda v: (items[v].get('id') or f"NEW {items[v].get('label')}") if isinstance(v, str) and v in items else v
    new = [e.get('label') for e in items.values() if not e.get('id')]
    if new:
        print('   new items:', new)
    for k, e in payload.items():
        if k.startswith('RELATION') and e.get('exists') != 'true':
            st = e['payload']['statement']
            quals = [(pname.get(q['property']['id']), ident(q['value']['content'])) for q in st.get('qualifiers', [])]
            line = f"   {e.get('exists'):8} {ident(e['url'].split('/')[-2])} {pname.get(st['property']['id'])} " \
                   f"{ident(st['value']['content'])} {quals}"
            if e.get('exists') == 'partial':
                line += f"  adds {[(pname.get(q['property']['id']), ident(q['value']['content'])) for q in e['add_qualifiers']]}"
            print(line)


if __name__ in ('__main__', 'django.core.management.commands.shell'):
    for case in os.environ.get('CASES', 'symbol').split(','):
        kind, item, edit = CASES[case]
        _, slug, qkey, item_type = TYPES[kind]
        title = f'TEMP staging round 2 {case}'
        Project.objects.filter(title=title).delete()
        p = new_project(slug, title)
        try:
            select(p, qkey, item_type, f'mardi:{QID[item]}', staging_item(item)['text'], 0)
            edit(p)
            res = {'qid': case}
            html = preview_and_payload(p, res)
            open(os.path.join(out, f'{case}.html'), 'w').write(html)
            json.dump(res, open(os.path.join(out, f'{case}.json'), 'w'), indent=1, default=str)
            print(f'{case}: dry run')
            report(res)
            if os.environ.get('DRY') == '1':
                p.delete()
            else:
                Membership.objects.create(project=p, user=User.objects.get(username=OWNER), role='owner')
                print(f'   project "{title}" (id {p.id}) ready for the export')
        except Exception:
            print(case, 'ERROR', traceback.format_exc())
            p.delete()
