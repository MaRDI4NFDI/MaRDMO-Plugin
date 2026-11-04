"""Symbols of formulas against the portal: missing quantity, one symbol for two quantities, completion.

Real portal models are filled and checked as in the interview; the export
payload is built (nothing is posted) and its "in defining formula" statements
are reported.

Cases:

  S1  Taylor-Couette model Q6830616: the symbol a of Q6830684 has no "symbol
      represents" on the portal -> no quantity in the questionnaire, the
      checks and the preview ask for it
  S2  as S1, the user adds a quantity -> the portal statement is completed
      (partial, adds symbol represents)
  S3  as S2, the user gives a symbol of another formula another quantity
      (a symbol block deleted and added again) -> the export stops
  S4  model Q7257548: the formula Q6775622 has one symbol for two quantities
      on the portal -> the checks stop it

Environment: OUT (default results/symbols-<date>).
"""
import datetime, json, os, sys, traceback
HERE_ = os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests'))
sys.path.insert(0, HERE_)
os.environ['OUT'] = os.environ.get('OUT') or os.path.join(HERE_, 'results', f'symbols-{datetime.date.today()}')
from common import *  # noqa: F401,F403
from preview_edits import answer, portal, TEXTS
from preview_payload import preview_and_payload, out
from MaRDMO.getters import get_properties

TITLE = 'TEMP symbols'
PROPS = get_properties()
VELOCITY = 'Q7360710'   # fluid velocity, a quantity of the Taylor-Couette model


def formula_page(project, qid):
    """Set index of the formula page of *qid*."""
    return project.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/formulation/id',
                              external_id=f'mardi:{qid}').set_index


def elements(project, page):
    """{element index: (symbol, quantity external_id)} of a formula page."""
    found = {}
    for v in project.values.filter(snapshot=None, set_prefix=f'{page}|0|0',
                                   attribute__uri__in=[f'{BASE_URI}domain/formulation/element/symbol',
                                                       f'{BASE_URI}domain/formulation/element/quantity']):
        symbol, quantity = found.get(v.set_index, ('', ''))
        if v.attribute.uri.endswith('symbol'):
            symbol = v.text
        else:
            quantity = v.external_id
        found[v.set_index] = (symbol, quantity)
    return found


def symbol_statements(payload, qid):
    """The "in defining formula" RELATION entries of portal item *qid*: (symbol, quantity, exists, adds)."""
    items = {k: e for k, e in payload.items() if k.startswith('Item')}
    ident = lambda v: items[v].get('id') or f"NEW:{items[v].get('label')}" if v in items else v
    rows = []
    for k, e in payload.items():
        st = e.get('payload', {}).get('statement', {})
        if not k.startswith('RELATION') or st.get('property', {}).get('id') != PROPS['in defining formula']:
            continue
        if ident(e['url'].split('/')[-2]) != qid:
            continue
        quantity = [ident(q['value']['content']) for q in st.get('qualifiers', [])]
        adds = [ident(q['value']['content']) for q in e.get('add_qualifiers', [])]
        rows.append((st['value']['content'], quantity, e.get('exists'), adds))
    return rows


def run(case, model, edit, check):
    res = {'qid': f'{case}-{model}'}
    try:
        source, slug, qkey, item_type = TYPES['model']
        p = new_project(slug, TITLE)
        TEXTS.update(labels(source, [model]))
        select(p, qkey, item_type, f'{source}:{model}', TEXTS[model], 0)
        edit(p)
        html = preview_and_payload(p, res)
        open(os.path.join(out, f"{res['qid']}.html"), 'w').write(html)
        json.dump(res, open(os.path.join(out, f"{res['qid']}.json"), 'w'), indent=1, default=str)
        result, ok = check(p, res, html)
        print(f"{case}  {result}{'' if ok else '   <-- differs'}", flush=True)
        return {'case': case, 'result': result, 'ok': ok}
    except Exception:
        print(case, 'ERROR', traceback.format_exc())
        return {'case': case, 'result': 'ERROR', 'ok': False}
    finally:
        Project.objects.filter(title=TITLE).delete()


def unchanged(p):
    pass


def check_s1(p, res, html):
    page = formula_page(p, 'Q6830684')
    els = elements(p, page)
    asks = [m for m in res.get('messages', []) if 'Missing Formula Quantity' in str(m)]
    ok = els == {0: ('a', '')} and bool(asks) and 'MISSING QUANTITY OR QUANTITY KIND' in html \
        and 'No Label Provided' not in html
    return f'elements {els}, check: {asks[:1]}, preview asks: {"MISSING QUANTITY OR QUANTITY KIND" in html}', ok


def add_quantity(p):
    page = formula_page(p, 'Q6830684')
    TEXTS.update(labels('mardi', [VELOCITY]))
    answer(p, 'formulation/element/quantity', signal=True, set_prefix=f'{page}|0|0', set_index=0,
           **portal(VELOCITY))


def check_s2(p, res, html):
    rows = symbol_statements(res.get('payload') or {}, 'Q6830684')
    return f'statements {rows} (export: {res.get("export message", "")[:80]})', \
        rows == [('a', [VELOCITY], 'partial', [VELOCITY])]


def other_quantity(p):
    """As S2, and a formula of the model whose symbol has a portal quantity gets another one."""
    add_quantity(p)
    for value in p.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/formulation/element/quantity'):
        if value.external_id.startswith('mardi:') and value.external_id != f'mardi:{VELOCITY}':
            value.text, value.external_id = TEXTS.get(VELOCITY) or labels('mardi', [VELOCITY])[VELOCITY], \
                f'mardi:{VELOCITY}'
            value.save()
            return
    raise RuntimeError('no symbol with a portal quantity')


def check_s3(p, res, html):
    message = str(res.get('export message', ''))
    return f'export: {message[:160]}', 'already stands for' in message


def check_s4(p, res, html):
    several = [m for m in res.get('messages', []) if 'stands for several quantities' in str(m)]
    return f'check: {several[:1]}, preview marks: {html.count("SYMBOL STANDS FOR SEVERAL QUANTITIES")}', \
        bool(several) and 'SYMBOL STANDS FOR SEVERAL QUANTITIES' in html


CASES = [('S1', 'Q6830616', unchanged, check_s1), ('S2', 'Q6830616', add_quantity, check_s2),
         ('S3', 'Q6830616', other_quantity, check_s3), ('S4', 'Q7257548', unchanged, check_s4)]


if __name__ in ('__main__', 'django.core.management.commands.shell'):
    report = []
    try:
        for case in CASES:
            report.append(run(*case))
    finally:
        Project.objects.filter(title=TITLE).delete()
        json.dump(report, open(os.path.join(out, 'report.json'), 'w'), indent=1, default=str)
        print('\nresults:', out)
        print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
