"""Render the preview and build the export payload per item, for preview_compare.py.

As in the interview, the preview runs first (it also fetches publication data
into the project), then the export payload is built from the same project.
Nothing is posted.  Per item, results/<OUT>/ holds
- <qid>.html:  the rendered preview (the catalog template, as on the export page)
- <qid>.json:  answers of both modes, check messages, payload (built also when
               the checks fail), export message or crash
and properties.json maps property names to IDs for the comparison.

Environment: TYPE (model, wikidata, algorithm, workflow; default model),
ITEMS (a list in items.json, default the TYPE list), QIDS (comma-separated,
instead of ITEMS), LIMIT, MOCK=1 (workflow with the mock usages of
workflow_mock.py, scenario "base"), OUT (default results/preview-<TYPE>,
with MOCK results/preview-workflow-mock).
"""
import datetime, json, os, sys, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
from common import *  # noqa: F401,F403
import MaRDMO
from django.core.cache import cache
from django.template.loader import render_to_string
from MaRDMO import main as mardmo_main
from MaRDMO.checks import Checks
from MaRDMO.getters import get_item_url, get_properties
from MaRDMO.main import MaRDMOExportProvider, _CATALOG_PREPARE_MAP

TITLE = 'TEMP preview'
KIND = os.environ.get('TYPE', 'model')
qids = (os.environ['QIDS'].split(',') if os.environ.get('QIDS')
        else json.load(open(os.path.join(HERE, 'items.json')))[os.environ.get('ITEMS', KIND)])
if os.environ.get('LIMIT'):
    qids = qids[:int(os.environ['LIMIT'])]
MOCK = os.environ.get('MOCK') == '1'
if MOCK:
    import workflow_mock   # replaces the process step query with real data plus mock usages
out = os.environ.get('OUT') or os.path.join(HERE, 'results', f"preview-{KIND}{'-mock' if MOCK else ''}")
os.makedirs(out, exist_ok=True)
json.dump(get_properties(), open(os.path.join(out, 'properties.json'), 'w'), indent=1)
print('code from', MaRDMO.__file__, '->', out)


def preview_and_payload(project, res):
    """Fill res with the preview (returned as HTML) and the payload of project."""
    slug = project.catalog.uri.rsplit('/', 1)[1]
    cache.clear()
    provider = MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, options = provider.get_post_data('preview')
    res['answers preview'] = answers
    html = render_to_string(mardmo_main.CATALOG_TEMPLATE_MAP[slug], {
        'answers': answers, 'option': options, 'title': project.title,
        'mardiURI': get_item_url('mardi'), 'wikidataURI': get_item_url('wikidata')})
    answers, _ = provider.get_post_data()
    res['answers'] = answers
    _, prepare_class, check_method = _CATALOG_PREPARE_MAP[slug]
    res['messages'] = [str(e) for e in getattr(Checks(), check_method)(
        project=project, data=answers, catalog=str(project.catalog)) or []]
    # also when the checks fail: portal items often lack what the checks ask of new ones
    try:
        res['payload'], _ = prepare_class().export(answers, get_url('mardi', 'uri'))
    except (ValueError, KeyError) as e:
        res['export message'] = [str(a) for a in e.args]
    except Exception:
        res['export crash'] = traceback.format_exc()
    return html


if __name__ in ('__main__', 'django.core.management.commands.shell'):
    source, slug, qkey, item_type = TYPES[KIND]
    texts = labels(source, qids)
    try:
        for number, qid in enumerate(qids, 1):
            res = {'qid': qid, 'source': source, 'time': str(datetime.datetime.now())}
            html = ''
            try:
                p = new_project(slug, TITLE)
                select(p, qkey, item_type, f'{source}:{qid}', texts[qid], 0)
                html = preview_and_payload(p, res)
            except Exception:
                res['error'] = traceback.format_exc()
            finally:
                Project.objects.filter(title=TITLE).delete()
            open(os.path.join(out, f'{qid}.html'), 'w').write(html)
            json.dump(res, open(os.path.join(out, f'{qid}.json'), 'w'), indent=1, default=str)
            print(f"{number:3}/{len(qids)} {qid:11} preview: {len(html):7} chars  "
                  f"payload: {len(res['payload']) if 'payload' in res else '-':>4}"
                  f"{'  EXPORT CRASH ' + res['export crash'].strip().splitlines()[-1] if 'export crash' in res else ''}"
                  f"{'  ERROR ' + res['error'].strip().splitlines()[-1] if 'error' in res else ''}", flush=True)
    finally:
        if MOCK:
            workflow_mock.workflow_handlers._fetch_by_source = workflow_mock._real_fetch
        Project.objects.filter(title=TITLE).delete()
        print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
