"""Fill a project per item from the portal and save answers, check messages and payload.

First half of the round-trip test: everything that needs the portal is
collected once here, the comparison runs offline on the saved files.

Per item, results/<OUT>/<qid>.json holds
- answers:  what get_post_data returns (the export reads this)
- messages: MaRDMO's check messages
- payload:  the export payload, also when the checks fail (nothing is posted)

Environment: TYPE (model, wikidata, algorithm, workflow; default model),
ITEMS (a list in items.json, default the TYPE list), QIDS (comma-separated,
instead of ITEMS), LIMIT, OUT (default
results/roundtrip-<TYPE>).
"""
import datetime, json, os, sys, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
from common import *  # noqa: F401,F403
import MaRDMO
from django.core.cache import cache
from MaRDMO.checks import Checks
from MaRDMO.main import MaRDMOExportProvider, _CATALOG_PREPARE_MAP

TITLE = 'TEMP roundtrip'
KIND = os.environ.get('TYPE', 'model')
qids = (os.environ['QIDS'].split(',') if os.environ.get('QIDS')
        else json.load(open(os.path.join(HERE, 'items.json')))[os.environ.get('ITEMS', KIND)])
if os.environ.get('LIMIT'):
    qids = qids[:int(os.environ['LIMIT'])]
out = os.environ.get('OUT') or os.path.join(HERE, 'results', f'roundtrip-{KIND}')
os.makedirs(out, exist_ok=True)
print('code from', MaRDMO.__file__, '->', out)

source, slug, qkey, item_type = TYPES[KIND]
texts = labels(source, qids)
try:
    for number, qid in enumerate(qids, 1):
        res = {'qid': qid, 'source': source, 'time': str(datetime.datetime.now())}
        try:
            p = new_project(slug, TITLE)
            select(p, qkey, item_type, f'{source}:{qid}', texts[qid], 0)
            cache.clear()
            provider = MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
            provider.project, provider.snapshot = p, None
            answers, _ = provider.get_post_data()
            res['answers'] = answers
            _, prepare_class, check_method = _CATALOG_PREPARE_MAP[slug]
            res['messages'] = [str(e) for e in getattr(Checks(), check_method)(
                project=p, data=answers, catalog=str(p.catalog)) or []]
            # also when the checks fail: portal items often lack what the checks ask of new ones
            try:
                res['payload'], _ = prepare_class().export(answers, get_url('mardi', 'uri'))
            except (ValueError, KeyError) as e:
                res['export message'] = [str(a) for a in e.args]
            except Exception:
                res['export crash'] = traceback.format_exc()
        except Exception:
            res['error'] = traceback.format_exc()
        finally:
            Project.objects.filter(title=TITLE).delete()
        json.dump(res, open(os.path.join(out, f'{qid}.json'), 'w'), indent=1, default=str)
        print(f"{number:3}/{len(qids)} {qid:11} messages: {len(res.get('messages', [])):3}  "
              f"payload: {len(res['payload']) if 'payload' in res else '-':>4}"
              f"{'  EXPORT CRASH ' + res['export crash'].strip().splitlines()[-1] if 'export crash' in res else ''}"
              f"{'  ERROR ' + res['error'].strip().splitlines()[-1] if 'error' in res else ''}", flush=True)
finally:
    Project.objects.filter(title=TITLE).delete()
    print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
