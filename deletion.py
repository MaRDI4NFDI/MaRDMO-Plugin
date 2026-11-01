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

Environment: ITEMS (a list in items.json instead of the four default items,
e.g. model_all), QUICK=1 (no checks before deleting, one line per item),
RDMO_FILTER_SET=fixed (patch RDMO's filter_set bug in this process only, see
~/Work/RDMO-bugs), OUT (default results/deletion-<date>).
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
if os.environ.get('ITEMS'):   # e.g. ITEMS=model_all: every model from items.json
    DELETION_ITEMS = [('model', qid) for qid in json.load(open(os.path.join(HERE, 'items.json')))[os.environ['ITEMS']]]
QUICK = os.environ.get('QUICK') == '1'   # no checks/export before deleting, one line per item
RDMO_FILTER_SET = os.environ.get('RDMO_FILTER_SET', 'original')
HIDDEN_BY_SET_INDEX = {a for a in BY_SET_INDEX if a.startswith('domain/publication/')}
out_base = os.environ.get('OUT') or os.path.join(HERE, 'results', f'deletion-{datetime.date.today()}')
os.makedirs(os.path.dirname(out_base), exist_ok=True)
print('code from', MaRDMO.__file__)

if RDMO_FILTER_SET == 'fixed':
    # RDMO's filter_set also matches set_prefix '10', '11', ... for set 1 (see ~/Work/RDMO-bugs);
    # patched in this process only, so the test shows MaRDMO's behaviour as with a fixed RDMO
    from django.db.models import Q
    from rdmo.projects.managers import ValueQuerySet
    _original_filter_set = ValueQuerySet.filter_set

    def _fixed_filter_set(self, set_value):
        prefix = (f'{set_value.set_prefix}|{set_value.set_index}' if set_value.set_prefix
                  else str(set_value.set_index))
        return _original_filter_set(self, set_value).filter(
            Q(set_prefix=set_value.set_prefix, set_index=set_value.set_index) |
            Q(set_prefix=prefix) | Q(set_prefix__startswith=f'{prefix}|'))
    ValueQuerySet.filter_set = _fixed_filter_set
print('RDMO filter_set:', RDMO_FILTER_SET)


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


def rdmo_bug_hits(values, below, k):
    """Values the unfixed RDMO filter_set would delete outside set k."""
    return sum(1 for attr, prefix, *_ in values
               if attr in below and prefix.startswith(str(k)) and prefix != str(k) and not prefix.startswith(f'{k}|'))


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


results = {'started': str(datetime.datetime.now()), 'rdmo filter_set': RDMO_FILTER_SET, 'items': {}}
texts = {}
for source in {TYPES[kind][0] for kind, _ in DELETION_ITEMS}:
    texts.update({(source, q): t for q, t in labels(source, [q for k, q in DELETION_ITEMS if TYPES[k][0] == source]).items()})
log = (lambda *a, **k: None) if QUICK else print
try:
    for number, (kind, qid) in enumerate(DELETION_ITEMS, 1):
        source, slug, qkey, item_type = TYPES[kind]
        res = results['items'][f'{kind}:{qid}'] = {'deleted': {}}
        log(f'\n== {kind} {qid}')
        try:
            text = texts[(source, qid)]
            p = new_project(slug, TITLE)
            select(p, qkey, item_type, f'{source}:{qid}', text, 0)
            first = dump(p)
            res['values'] = len(first)
            if not QUICK:
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
                res.setdefault('deleted items', []).extend(v[5] or v[4] for v in want if v[0] == f'{set_attr}/id' and v[1] == '')
                entry = {'sets': count, 'deleted set': k, 'values gone': len(gone),
                         'unfixed RDMO would also delete': rdmo_bug_hits(before, below[set_attr], k)}
                if gone == want:
                    entry['result'] = 'exactly the set'
                else:
                    entry['result'] = 'WRONG'
                    entry['gone but outside the set'] = sorted(gone - want)[:10]
                    entry['outside count'] = len(gone - want)
                    entry['left over from the set'] = sorted(want - gone)[:10]
                    entry['left over count'] = len(want - gone)
                res['deleted'][set_attr] = entry
                log(f"  delete {set_attr:28} set {k:2} of {count:3}: {entry['result']:16} "
                      f"({len(gone)} values{', ' + str(entry.get('outside count')) + ' outside' if entry.get('outside count') else ''}"
                      f"{', ' + str(entry.get('left over count')) + ' left over' if entry.get('left over count') else ''})")
            res['after deletion'] = run_after(p)
            log('  after deletion:', {k: (v if not str(k).startswith('CRASH') else v.strip().splitlines()[-1]) for k, v in res['after deletion'].items()})
            select(p, qkey, item_type, f'{source}:{qid}', text, 0, again=True)
            restored = dump(p)
            missing = content(first, True) - content(restored, True)
            others = [m for m in missing if m[1] not in res.get('deleted items', [])]
            if not missing:
                res['restored'] = 'complete'
            elif not others:
                res['restored'] = {'result': 'deleted items reached only through other items not re-filled',
                                   'missing count': sum(missing.values()), 'missing items': sorted({m[1] for m in missing})}
            else:
                res['restored'] = {'result': 'VALUES OF OTHER ITEMS MISSING', 'missing count': sum(missing[m] for m in others),
                                   'missing': [list(m) for m in others[:10]], 'missing items': sorted({m[1] for m in others})}
            log('  re-selected:', res['restored'] if isinstance(res['restored'], str) else res['restored']['result'])
            if QUICK:
                wrong = [a for a, e in res['deleted'].items() if e['result'] != 'exactly the set']
                crash = [k for k in res['after deletion'] if k.startswith('CRASH')]
                r = res['restored']
                print(f"{number:3}/{len(DELETION_ITEMS)} {qid:11} {len(first):5} values  deleted in {len(res['deleted'])} sections: "
                      f"{'ok' if not wrong else 'WRONG ' + ','.join(wrong)}  after: {'CRASH ' + ','.join(crash) if crash else 'ok'}  "
                      f"re-selected: {r if isinstance(r, str) else ('deleted ' + str(len(r['missing items'])) + ' not re-filled' if r['result'].startswith('deleted') else r['result'])}", flush=True)
        except Exception:
            res['error'] = traceback.format_exc()
            print(f'{qid}: ERROR', res['error'].strip().splitlines()[-1], flush=True)
        finally:
            Project.objects.filter(title=TITLE).delete()
finally:
    Project.objects.filter(title=TITLE).delete()
    results['finished'] = str(datetime.datetime.now())
    json.dump(results, open(out_base + '.json', 'w'), indent=1, default=str)
    print('\nresults:', out_base + '.json')
    print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
