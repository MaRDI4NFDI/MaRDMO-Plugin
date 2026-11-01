"""Idempotence and order of filling items from the MaRDI Portal and Wikidata.

Fills are triggered like in the interview: an ID value is saved and RDMO's
``value_created`` / ``value_updated`` signal is sent, so the MaRDMO router
runs the real handler.  Read-only towards the portals; every temporary
project is deleted at the end.

Cases per item (``items.json``):

- twice:  fill, then re-select the same item -> values must be identical
- manual: delete one relatant value by hand, re-select the item it belongs
          to (the selected item or one filled with it) -> content must match
          the first fill again
Cases per group of three items:

- order:  fill A, B, C in one project and C, B, A in another -> same content

Content comparison ignores set and collection numbers: each value is keyed by
the item its set belongs to.  "strict" also keeps the inner numbers below the
item, "loose" drops them.

Environment: TYPES (default all), LIMIT (items per type), CASES (items,order),
GROUPS (order groups per type, default 3), OUT (default results/idempotence-<date>).
"""
import collections, datetime, json, os, random, sys, time, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
from common import *  # noqa: F401,F403  (helpers, TYPES, HERE, PAUSE)
import MaRDMO

TITLE = 'TEMP idempotence'
ITEMS = json.load(open(os.path.join(HERE, 'items.json')))
types = os.environ.get('TYPES', ','.join(TYPES)).split(',')
limit = int(os.environ.get('LIMIT', 0)) or None
groups = int(os.environ.get('GROUPS', 3))
cases = os.environ.get('CASES', 'items,order').split(',')
out_base = os.environ.get('OUT') or os.path.join(HERE, 'results', f'idempotence-{datetime.date.today()}')
os.makedirs(os.path.dirname(out_base), exist_ok=True)
print('code from', MaRDMO.__file__)


def manual_target(values):
    """A relatant value to delete by hand (deterministic choice)."""
    cands = [v for v in values if 'relatant' in v[0] and v[5]]
    return random.Random(0).choice(cands) if cands else None


results = {'started': str(datetime.datetime.now()), 'items': {}, 'order': {}}
try:
    for kind in types:
        source, slug, qkey, item_type = TYPES[kind]
        qids = ITEMS[kind][:limit]
        texts = labels(source, qids)
        print(f'\n== {kind}: {len(qids)} items')
        for qid in (qids if 'items' in cases else []):
            res = results['items'].setdefault(kind, {})[qid] = {}
            t = time.perf_counter()
            try:
                p = new_project(slug, TITLE)
                select(p, qkey, item_type, f'{source}:{qid}', texts[qid], 0)
                first = dump(p)
                select(p, qkey, item_type, f'{source}:{qid}', texts[qid], 0, again=True)
                second = dump(p)
                res['values'] = len(first)
                res['twice'] = 'identical' if first == second else diff(collections.Counter(first), collections.Counter(second))
                target = manual_target(second)
                if target:
                    attr, prefix, sidx, cidx = target[:4]
                    Value.objects.filter(project=p, snapshot=None, attribute__uri=BASE_URI + attr, set_prefix=prefix,
                                         set_index=sidx, collection_index=cidx).delete()
                    # re-select the item the relatant belongs to (the selected item or one filled with it)
                    owner = Value.objects.get(project=p, snapshot=None, set_prefix='', set_index=int(prefix.split('|')[0]),
                                              attribute__uri=f"{BASE_URI}domain/{attr.split('/')[1]}/id")
                    reselect(p, owner)
                    third = dump(p)
                    res['manual'] = {'deleted': list(target), 'reselected': owner.external_id}
                    if third == first:
                        res['manual']['result'] = 'identical'
                    elif content(third) == content(first):
                        res['manual']['result'] = 'same content, other numbers'
                    elif not content(first, True) - content(third, True):
                        res['manual']['result'] = 'restored, with leftovers'
                        res['manual']['leftovers'] = diff(content(first), content(third))['only_second']
                    else:
                        res['manual']['result'] = 'NOT restored'
                        res['manual']['diff'] = diff(content(first), content(third))
                else:
                    res['manual'] = 'no relatant to delete'
            except Exception:
                res['error'] = traceback.format_exc(limit=4)
            finally:
                Project.objects.filter(title=TITLE).delete()
            short = lambda r: r if isinstance(r, str) else ('DIFF' if isinstance(r, dict) and 'counts' in r else r.get('result') if isinstance(r, dict) else r)
            print(f"{qid:11} {res.get('values', '-'):>5} values  twice: {short(res.get('twice'))!s:10}  "
                  f"manual: {short(res.get('manual'))!s:28} {round(time.perf_counter() - t)} s"
                  f"{'  ERROR ' + res['error'].splitlines()[-1] if 'error' in res else ''}")

        for g in range(min(groups, len(qids) // 3) if 'order' in cases else 0):
            group = qids[3 * g:3 * g + 3]
            res = results['order'].setdefault(kind, {})['+'.join(group)] = {}
            try:
                dumps = []
                for order in (group, group[::-1]):
                    p = new_project(slug, TITLE)
                    for i, qid in enumerate(order):
                        select(p, qkey, item_type, f'{source}:{qid}', texts[qid], i)
                    dumps.append(dump(p))
                    p.delete()
                a, b = dumps
                res['values'] = [len(a), len(b)]
                if content(a) == content(b):
                    res['result'] = 'same content'
                elif content(a, True) == content(b, True):
                    res['result'] = 'same values, other inner numbers'
                    res['renumbered'] = sorted({k[0] for k in (content(a) - content(b)) + (content(b) - content(a))})
                else:
                    res['result'] = 'DIFF'
                    res['strict'] = diff(content(a), content(b))
                    res['loose'] = diff(content(a, True), content(b, True))
                ids = collections.Counter(v[5] for v in a if v[0].endswith('/id') and v[1] == '' and v[5])
                res['items_in_project'] = len(ids)
            except Exception:
                res['error'] = traceback.format_exc(limit=4)
            finally:
                Project.objects.filter(title=TITLE).delete()
            r = res.get('result')
            print(f"order {'+'.join(group)}: {r} "
                  f"({res.get('values')} values, {res.get('items_in_project')} items)"
                  f"{'  ERROR ' + res['error'].splitlines()[-1] if 'error' in res else ''}")
finally:
    Project.objects.filter(title=TITLE).delete()
    results['finished'] = str(datetime.datetime.now())
    json.dump(results, open(out_base + '.json', 'w'), indent=1)
    print('\nresults:', out_base + '.json')
    print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
