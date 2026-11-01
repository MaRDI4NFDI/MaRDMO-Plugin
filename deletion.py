"""Deleting sets the way the interview does, then checks, export, preview and re-selection.

For every item in DELETION_ITEMS a temporary project is filled; then, section
by section, one set is deleted like RDMO's ``delete_set`` does it (the set
value, then ``Value.objects.filter_set``; MaRDMO's post-delete handlers run).
A section with 12 or more sets loses set 1, so sets 10-19 show whether
anything outside the deleted set disappears; other sections lose set 0.

Cases per item:

- deleted:  exactly the values of the deleted set are gone (its questions and
            sub-sets; for publications also the hidden citation data removed
            by MaRDMO's delete handler), nothing else
- after:    checks, export payload (nothing is posted) and preview run on the
            reduced project without crashing
- restored: the main item is selected again; afterwards every value of the
            first filling is there again (content compared without numbers)

Environment: OUT (default results/deletion-<date>).
"""
import collections, datetime, json, os, sys, traceback
sys.path.insert(0, os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests')))
from common import *  # noqa: F401,F403
import MaRDMO
from django.core.cache import cache
from django.template.loader import render_to_string
from MaRDMO import main as mardmo_main
from MaRDMO.checks import Checks
from MaRDMO.getters import get_item_url

TITLE = 'TEMP deletion'
DELETION_ITEMS = [  # (type, qid)
    ('model', 'Q6534342'), ('wikidata', 'Q3660888'), ('algorithm', 'Q6825308'), ('workflow', 'Q6032641'),
]
HIDDEN_BY_SET_INDEX = {a for a in BY_SET_INDEX if a.startswith('domain/publication/')}
out_base = os.environ.get('OUT') or os.path.join(HERE, 'results', f'deletion-{datetime.date.today()}')
os.makedirs(os.path.dirname(out_base), exist_ok=True)
print('code from', MaRDMO.__file__)


def catalog_attributes(project):
    """{set attribute path: paths of all questions below it} for the project's catalog."""
    catalog = project.catalog
    catalog.prefetch_elements()
    below = collections.defaultdict(set)
    for element in catalog.pages + catalog.questions:
        if element.attribute and element.is_collection:
            for descendant in element.descendants:
                if descendant.attribute:
                    below[element.attribute.uri.replace(BASE_URI, '')].add(descendant.attribute.uri.replace(BASE_URI, ''))
    return below


def expected_gone(values, set_attr, below, k):
    """Values of set k of set_attr and its sub-sets, worked out independently of RDMO."""
    gone = set()
    for v in values:
        attr, prefix, sidx = v[0], v[1], v[2]
        in_questions = attr == set_attr or attr in below
        in_set = (prefix == '' and sidx == k) or prefix == str(k) or prefix.startswith(f'{k}|')
        if in_questions and in_set:
            gone.add(v)
        if set_attr == 'domain/publication' and attr in HIDDEN_BY_SET_INDEX and sidx == k:
            gone.add(v)
    return gone


def delete_set(project, set_attr, k):
    """What RDMO's ProjectValueViewSet.delete_set does."""
    set_value = Value.objects.get(project=project, snapshot=None, attribute__uri=BASE_URI + set_attr,
                                  set_prefix='', set_index=k)
    set_value.delete()
    Value.objects.filter(project=project).filter_set(set_value).delete()


def run_after(project):
    """Checks, export payload and preview on the current project; returns problems."""
    from MaRDMO.main import MaRDMOExportProvider, _CATALOG_PREPARE_MAP
    slug = project.catalog.uri.rsplit('/', 1)[1]
    report = {}
    cache.clear()
    provider = MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project = project
    provider.snapshot = None
    try:
        answers, _ = provider.get_post_data()
        _, prepare_class, check_method = _CATALOG_PREPARE_MAP[slug]
        errors = getattr(Checks(), check_method)(project=project, data=answers, catalog=str(project.catalog))
        report['check messages'] = len(errors or [])
        if not errors:
            try:
                payload, _ = prepare_class().export(answers, get_url('mardi', 'uri'))
                report['payload items'] = len(payload)
            except (ValueError, KeyError) as e:
                report['export message'] = [str(a)[:200] for a in e.args]
    except Exception:
        report['CRASH checks/export'] = traceback.format_exc(limit=5)
    try:
        answers, options = provider.get_post_data('preview')
        html = render_to_string(mardmo_main.CATALOG_TEMPLATE_MAP[slug], {
            'answers': answers, 'option': options, 'title': project.title,
            'mardiURI': get_item_url('mardi'), 'wikidataURI': get_item_url('wikidata')})
        report['preview characters'] = len(html)
        report['preview NOT FOUND marks'] = html.count('NOT FOUND')
    except Exception:
        report['CRASH preview'] = traceback.format_exc(limit=5)
    return report


results = {'started': str(datetime.datetime.now()), 'items': {}}
try:
    for kind, qid in DELETION_ITEMS:
        source, slug, qkey, item_type = TYPES[kind]
        res = results['items'][f'{kind}:{qid}'] = {'deleted': {}}
        print(f'\n== {kind} {qid}')
        try:
            text = labels(source, [qid])[qid]
            p = new_project(slug, TITLE)
            select(p, qkey, item_type, f'{source}:{qid}', text, 0)
            first = dump(p)
            res['values'] = len(first)
            res['before deletion'] = run_after(p)
            below = catalog_attributes(p)
            main_set = get_questions(qkey)[item_type]['uri']
            sets = collections.Counter(v[0] for v in first if v[1] == '' and v[0] in below and v[0] != main_set)
            for set_attr, count in sorted(sets.items()):
                k = 1 if count >= 12 else 0
                before = dump(p)
                want = expected_gone(before, set_attr, below[set_attr], k)
                delete_set(p, set_attr, k)
                after = dump(p)
                gone = set(before) - set(after)
                entry = {'sets': count, 'deleted set': k, 'values gone': len(gone)}
                if gone == want:
                    entry['result'] = 'exactly the set'
                else:
                    entry['result'] = 'WRONG'
                    entry['gone but outside the set'] = sorted(gone - want)[:10]
                    entry['outside count'] = len(gone - want)
                    entry['left over from the set'] = sorted(want - gone)[:10]
                    entry['left over count'] = len(want - gone)
                res['deleted'][set_attr] = entry
                print(f"  delete {set_attr:28} set {k:2} of {count:3}: {entry['result']:16} "
                      f"({len(gone)} values{', ' + str(entry.get('outside count')) + ' outside' if entry.get('outside count') else ''}"
                      f"{', ' + str(entry.get('left over count')) + ' left over' if entry.get('left over count') else ''})")
            res['after deletion'] = run_after(p)
            print('  after deletion:', {k: (v if not str(k).startswith('CRASH') else v.strip().splitlines()[-1]) for k, v in res['after deletion'].items()})
            select(p, qkey, item_type, f'{source}:{qid}', text, 0, again=True)
            restored = dump(p)
            missing = content(first, True) - content(restored, True)
            res['restored'] = 'complete' if not missing else {'missing count': sum(missing.values()), 'missing': [list(m) for m in list(missing)[:10]]}
            print('  re-selected:', res['restored'] if isinstance(res['restored'], str) else f"{res['restored']['missing count']} values missing")
        except Exception:
            res['error'] = traceback.format_exc()
            print(res['error'])
        finally:
            Project.objects.filter(title=TITLE).delete()
finally:
    Project.objects.filter(title=TITLE).delete()
    results['finished'] = str(datetime.datetime.now())
    json.dump(results, open(out_base + '.json', 'w'), indent=1, default=str)
    print('\nresults:', out_base + '.json')
    print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
