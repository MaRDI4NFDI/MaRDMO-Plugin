"""Helpers shared by the dev-test scripts (run inside ``manage.py shell``)."""
import collections, logging, os, time
logging.disable(logging.WARNING)
import requests
from django.contrib.sites.models import Site
from rdmo.projects.models import Project, Value
from rdmo.projects.signals import value_created, value_updated
from rdmo.questions.models import Catalog
from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_questions, get_url
from MaRDMO.helpers import value_editor

HERE = os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests'))  # run via manage.py shell, no __file__
PAUSE = 2
PORTAL = 'https://portal.mardi4nfdi.de'
# the tests use the test items of the MaRDI Portal; with MARDMO_PROVIDER set to another
# Wikibase (staging) they would fail or compare against other data
STAGING = 'https://staging.mardi4nfdi.org'
if get_url('mardi', 'uri') == STAGING and os.environ.get('STAGING') == '1':
    # only scripts made for staging (staging_projects.py) are run like this
    print(f'NOTE: MaRDMO is configured for {STAGING} (STAGING=1)')
elif get_url('mardi', 'uri') != PORTAL:
    raise SystemExit(f"MaRDMO is configured for {get_url('mardi', 'uri')}, not {PORTAL} "
                     '(MARDMO_PROVIDER in config/settings/local.py); stopped.')
TYPES = {  # name: (source, catalog slug, questions key, item type)
    'model':     ('mardi',    'mardmo-model-catalog',                      'model',     'Mathematical Model'),
    'wikidata':  ('wikidata', 'mardmo-model-catalog',                      'model',     'Mathematical Model'),
    'algorithm': ('mardi',    'mardmo-algorithm-catalog',                  'algorithm', 'Algorithm'),
    'workflow':  ('mardi',    'mardmo-interdisciplinary-workflow-catalog', 'workflow',  'Workflow'),
}


def labels(source, qids):
    """Return {qid: 'label (description) [source]'} with one API call per 50 items."""
    texts = {}
    for i in range(0, len(qids), 50):
        r = requests.get(get_url(source, 'api'), params={
            'action': 'wbgetentities', 'ids': '|'.join(qids[i:i + 50]), 'props': 'labels|descriptions',
            'languages': 'en', 'format': 'json'}, headers={'User-Agent': 'MaRDMO-test (read-only)'}, timeout=30)
        for qid, e in r.json()['entities'].items():
            texts[qid] = (f"{e.get('labels', {}).get('en', {}).get('value', qid)} "
                          f"({e.get('descriptions', {}).get('en', {}).get('value', '')}) [{source}]")
        time.sleep(PAUSE)
    return texts


def new_project(slug, title):
    return Project.objects.create(title=title, catalog=Catalog.objects.get(uri__endswith=slug),
                                  site=Site.objects.get_current())


def select(project, qkey, item_type, external_id, text, set_index, again=False):
    """Save the item's ID value and send the signal the interview would send."""
    q = get_questions(qkey)[item_type]
    value_editor(project=project, uri=f'{BASE_URI}{q["uri"]}', info={'text': f'X{set_index + 1}', 'set_index': set_index})
    value, _ = value_editor(project=project, uri=f'{BASE_URI}{q["ID"]["uri"]}',
                            info={'text': text, 'external_id': external_id, 'set_index': set_index})
    (value_updated if again else value_created).send(sender=Value, instance=value)
    time.sleep(PAUSE)


def reselect(project, value):
    """Send value_updated for an existing ID value, as if it was selected again."""
    value_updated.send(sender=Value, instance=value)
    time.sleep(PAUSE)


def dump(project):
    return sorted((v.attribute.uri.replace(BASE_URI, ''), v.set_prefix, v.set_index, v.collection_index or 0,
                   v.text or '', v.external_id or '', v.option.uri.rsplit('/', 1)[1] if v.option else '')
                  for v in project.values.filter(snapshot=None).select_related('attribute', 'option'))


def _by_set_index():
    """Attributes that belong to their item through set_index (questions.json: set_index without set_prefix)."""
    paths = set()
    for qkey in ('model', 'algorithm', 'workflow', 'publication'):
        for page in get_questions(qkey).values():
            for entry in page.values():
                if isinstance(entry, dict) and entry.get('set_index') and not entry.get('set_prefix') \
                        and not entry.get('external_id'):
                    paths.add(entry['uri'])
    return paths
BY_SET_INDEX = _by_set_index()


def content(values, loose=False):
    """Values keyed by the item their top-level set belongs to instead of by numbers.

    "strict" keeps the numbers below the item, "loose" drops them.
    """
    owner = {}  # (section, set_index) -> item
    for attr, prefix, sidx, _, text, ext, _ in values:
        parts = attr.split('/')
        if prefix == '' and len(parts) == 3 and parts[2] == 'id':
            owner[(parts[1], sidx)] = ext or text
    result = collections.Counter()
    for attr, prefix, sidx, cidx, text, ext, opt in values:
        parts = attr.split('/')
        section = parts[1] if len(parts) > 1 else ''
        if attr in BY_SET_INDEX:
            item = owner.get((section, sidx), f'?{sidx}')
            key = (attr, item, prefix, 0, cidx)
        elif prefix == '':
            item = owner.get((section, sidx), f'?{sidx}')
            if len(parts) == 2:   # set entry, its text is a running label (X1, MM1, ...)
                text = ''
            key = (attr, item, '', 0, 0)
        else:
            first, _, rest = prefix.partition('|')
            item = owner.get((section, int(first)), f'?{first}')
            key = (attr, item, rest, sidx, cidx)
        if loose:
            key = key[:2]
        result[key + (text, ext, opt)] += 1
    return result


def diff(a, b, n=8):
    only_a, only_b = a - b, b - a
    return {'only_first': [list(k) for k in list(only_a)[:n]], 'only_second': [list(k) for k in list(only_b)[:n]],
            'counts': [sum(only_a.values()), sum(only_b.values())]}


def gaps(values):
    """Collections whose indices do not run 0, 1, 2, ... within their set."""
    by_set = collections.defaultdict(list)
    for attr, prefix, sidx, cidx, *_ in values:
        by_set[(attr, prefix, sidx)].append(cidx)
    return sorted([*key, sorted(c)] for key, c in by_set.items() if sorted(c) != list(range(len(c))))
