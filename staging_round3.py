"""Round 3 of the staging cycle: unchanged imports of the test items must write nothing (dry run).

Each staging item of rounds 1 and 2 is filled into a new project as in the
interview and its export payload is built (nothing is posted); then
unchanged_export.py reports what an export would write -- it must be
nothing.  Staging is unreliable, so an item counts only if its payload was
built without a failed request: MaRDMO's warnings while filling (e.g.
"wbgetentities failed") or an unreachable check make the attempt fail.
Before every attempt the script waits until staging answers twice in a
row (MaRDMO's own retries cope with single failures; staging answered about
half of all requests on 2026-11-05, and longer runs of answers were rare);
failed attempts are repeated with growing pauses.

Needs MaRDMO configured for staging and STAGING=1.  Environment: ROUND3_ITEMS
(kind:QID,...), OUT (default results/staging-round3), ATTEMPTS (default 6).
"""
import json, logging, os, sys, time, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
os.environ['OUT'] = os.environ.get('OUT') or os.path.join(
    os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')), 'results', 'staging-round3')
import requests
from common import *  # noqa: F401,F403
from preview_payload import preview_and_payload, out
from unchanged_export import report

if get_url('mardi', 'uri') != STAGING:
    raise SystemExit('round 3 needs MaRDMO configured for staging (and STAGING=1); stopped.')

TITLE = 'TEMP staging round 3'
ITEMS = [spec.split(':') for spec in os.environ.get(
    'ROUND3_ITEMS', 'model:Q21993,model:Q21991,algorithm:Q21997,workflow:Q22005').split(',')]
ATTEMPTS = int(os.environ.get('ATTEMPTS', 6))
PAUSES = [120, 300, 600, 1200, 1200, 1200]   # seconds before attempt 2, 3, ...


class Warnings(logging.Handler):
    """Collects MaRDMO's warnings and errors of one attempt (failed requests while filling)."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.records = []

    def emit(self, record):
        if record.name.startswith('MaRDMO'):
            self.records.append(self.format(record))


def stable(needed=2, limit=1800):
    """Wait until staging answers *needed* times in a row; False after *limit* seconds."""
    end, ok = time.monotonic() + limit, 0
    while time.monotonic() < end:
        try:
            r = requests.get(get_url('mardi', 'api'), params={'action': 'wbgetentities', 'ids': 'Q1',
                             'props': 'info', 'format': 'json'}, headers={'User-Agent': 'MaRDMO-test (read-only)'},
                             timeout=20)
            ok = ok + 1 if r.status_code == 200 and 'entities' in r.json() else 0
        except (requests.RequestException, ValueError):
            ok = 0
        if ok >= needed:
            return True
        time.sleep(5 if ok else 60)
    return False


def attempt(kind, qid):
    """One unchanged import of *qid*; returns (result, problems)."""
    source, slug, qkey, item_type = TYPES[kind]
    handler = Warnings()
    logging.getLogger().addHandler(handler)
    res = {'qid': qid, 'source': source}
    try:
        text = labels(source, [qid])[qid]
        p = new_project(slug, TITLE)
        try:
            select(p, qkey, item_type, f'{source}:{qid}', text, 0)
            preview_and_payload(p, res)
        finally:
            p.delete()
    except Exception:
        res['error'] = traceback.format_exc()
    finally:
        logging.getLogger().removeHandler(handler)
    problems = list(handler.records)
    if 'error' in res:
        problems.append(res['error'].strip().splitlines()[-1])
    elif 'payload' not in res:
        problems.append(f"no payload: {res.get('export message') or res.get('export crash', '')[-200:]}")
    return res, problems


if __name__ in ('__main__', 'django.core.management.commands.shell'):
    for f in os.listdir(out):
        if f.endswith('.json') and f != 'properties.json':
            os.remove(os.path.join(out, f))
    done = []
    try:
        for kind, qid in ITEMS:
            for number in range(1, ATTEMPTS + 1):
                if number > 1:
                    time.sleep(PAUSES[number - 2])
                if not stable():
                    print(f'{qid}: attempt {number}, staging not stable for 30 minutes', flush=True)
                    continue
                res, problems = attempt(kind, qid)
                if not problems:
                    json.dump(res, open(os.path.join(out, f'{qid}.json'), 'w'), indent=1, default=str)
                    print(f'{qid}: ok (attempt {number})', flush=True)
                    done.append(qid)
                    break
                print(f'{qid}: attempt {number} failed: {problems[0][:160]}', flush=True)
            else:
                print(f'{qid}: GAVE UP after {ATTEMPTS} attempts', flush=True)
    finally:
        Project.objects.filter(title=TITLE).delete()
        print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
    print(f'\n{len(done)} of {len(ITEMS)} items imported without problems')
    report(out)
