'''Which statements are on the MaRDI Portal already: SPARQL against the item claims (#152).

The export asks the query service, 50 ``BIND(EXISTS ...)`` per query, which
statements of existing items are there (8.5 s for a model of 800 answers).
The claims of the items (wbgetentities, 50 per call) take 0.5 s.  Before
the export switches, both must decide the same for every statement.

Per portal item: a project is filled from the portal (test database), the
payload built without the check, then both decide every RELATION.  Every
10th item also gets altered copies of some statements (another value,
another qualifier value: new in both; one qualifier left out: there in both),
so "new" is compared too, not only "there".

Production portal, read-only, with pauses.  Runs with pytest in the plugin's
test environment:

    cd ~/Work/MaRDMO-Plugin
    QUESTIONNAIRE=~/Work/MaRDMO-Questionnaire/catalog pytest dev-tests/existence_api.py \
        --rootdir=. -c pyproject.toml -p no:cacheprovider -q --force-enable-socket

Environment: LISTS (items.json lists, default model_all,algorithm_all,wikidata,workflow),
ONLY (QIDs), LIMIT (per list), OUT (results/<OUT>, default existence-api).
An item with a result file is skipped (resume); results/<OUT>.log gets one line per item.

Needs the SPARQL check, so it runs on 0.8.0 before the switch (09dd40f).
Run of 2026-11-14 (1504 items: 235 models, 1253 algorithms, 15 Wikidata
models, the workflow): 69,844 statements, 1,151 of them altered copies,
0 differences, 0 errors; SPARQL 2033 s in all, the claims 197 s.
'''
import copy
import json
import os
import re
import time
import traceback

import pytest
from django.core.cache import cache

from MaRDMO import main
from MaRDMO.getters import get_url
from MaRDMO.payload import GeneratePayload, PortalUnavailable
from MaRDMO.queries import EXPORT_RETRY_WAITS, query_sparql
from tests.conftest import questionnaire  # noqa: F401
from tests.db.conftest import django_db_setup, project, select  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'results', os.environ.get('OUT', 'existence-api'))
LOG = OUT + '.log'
PAUSE = 1
QID_RE = re.compile(r'^Q\d+$')
KINDS = {  # list: (catalog, questions, page, source)
    'model_all': ('mardmo-model-catalog', 'model', 'Mathematical Model', 'mardi'),
    'model': ('mardmo-model-catalog', 'model', 'Mathematical Model', 'mardi'),
    'wikidata': ('mardmo-model-catalog', 'model', 'Mathematical Model', 'wikidata'),
    'algorithm_all': ('mardmo-algorithm-catalog', 'algorithm', 'Algorithm', 'mardi'),
    'algorithm': ('mardmo-algorithm-catalog', 'algorithm', 'Algorithm', 'mardi'),
    'workflow': ('mardmo-interdisciplinary-workflow-catalog', 'workflow', 'Workflow', 'mardi'),
}
LISTS = os.environ.get('LISTS', 'model_all,algorithm_all,wikidata,workflow').split(',')
items = json.load(open(os.path.join(HERE, 'items.json')))
CASES = []
for name in LISTS:
    qids = items[name][:int(os.environ['LIMIT'])] if os.environ.get('LIMIT') else items[name]
    CASES += [(name, qid) for qid in qids]
if os.environ.get('ONLY'):
    CASES = [case for case in CASES if case[1] in os.environ['ONLY'].split(',')]
os.makedirs(OUT, exist_ok=True)


# --- the decision from the claims (moves into payload.py with the switch)

def exists_in_claims(payload, entry, claims):
    ''''true' if a portal statement of the subject has the value and every qualifier of *entry*.

    A portal statement with more qualifiers matches too, as in the SPARQL
    check; merge_qualifiers decides on the meaning qualifiers afterwards.
    '''
    statement = entry['payload']['statement']
    subject = payload._resolve_item_reference(entry['url'].split('/')[-2])
    if not (isinstance(subject, str) and QID_RE.match(subject)):
        return 'false'
    value = payload._resolve_item_reference(statement['value']['content'])
    if value == '':
        return 'false'
    data_type = statement['property']['data_type']
    wanted = [(q['property']['id'], payload._resolve_item_reference(q['value']['content']),
               q['property']['data_type']) for q in statement.get('qualifiers', [])]
    if any(q_value == '' for _, q_value, _ in wanted):
        return 'false'
    for claim in claims.get(subject, {}).get(statement['property']['id'], []):
        if not payload._snak_matches(claim.get('mainsnak', {}), value, data_type):
            continue
        if all(any(payload._snak_matches(snak, q_value, q_type) for snak in claim.get('qualifiers', {}).get(q_prop, []))
               for q_prop, q_value, q_type in wanted):
            return 'true'
    return 'false'


# --- altered copies

def altered(entry):
    '''Copies of *entry*: (how, expected the same in both, copy).'''
    statement = entry['payload']['statement']
    data_type, value = statement['property']['data_type'], statement['value']['content']
    copies = []
    other = copy.deepcopy(entry)
    if data_type == 'wikibase-item' and isinstance(value, str) and QID_RE.match(value):
        other['payload']['statement']['value']['content'] = 'Q1'
        copies.append(('other value', other))
    elif data_type in ('string', 'external-id') and isinstance(value, str):
        other['payload']['statement']['value']['content'] = value + ' (altered)'
        copies.append(('other value', other))
    qualifiers = statement.get('qualifiers', [])
    items_q = [i for i, q in enumerate(qualifiers) if q['property']['data_type'] == 'wikibase-item'
               and isinstance(q['value']['content'], str) and QID_RE.match(q['value']['content'])]
    if items_q:
        other = copy.deepcopy(entry)
        other['payload']['statement']['qualifiers'][items_q[0]]['value']['content'] = 'Q1'
        copies.append(('other qualifier value', other))
    if qualifiers:
        other = copy.deepcopy(entry)
        del other['payload']['statement']['qualifiers'][0]
        copies.append(('qualifier left out', other))
    return copies


def describe(payload, entry):
    statement = entry['payload']['statement']
    return {'subject': payload._resolve_item_reference(entry['url'].split('/')[-2]),
            'property': statement['property']['id'], 'type': statement['property']['data_type'],
            'value': payload._resolve_item_reference(statement['value']['content']),
            'qualifiers': [(q['property']['id'], q['property']['data_type'],
                            payload._resolve_item_reference(q['value']['content']))
                           for q in statement.get('qualifiers', [])]}


def log(line):
    print(line, flush=True)
    with open(LOG, 'a') as handle:
        handle.write(line + '\n')


@pytest.mark.django_db
@pytest.mark.parametrize('name, qid', CASES)
def test_existence(name, qid, project, monkeypatch):  # noqa: F811
    path = os.path.join(OUT, f'{qid}.json')
    if os.path.exists(path):
        pytest.skip('done')
    catalog, qkey, page, source = KINDS[name]
    result = {'list': name, 'qid': qid}
    started = time.monotonic()
    try:
        cache.clear()
        documentation = project(catalog)
        select(documentation, qkey, page, f'{source}:{qid}', f'{qid} (x) [{source}]')
        provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
        provider.project, provider.snapshot = documentation, None
        answers, _ = provider.get_post_data()
        made, init = [], GeneratePayload.__init__

        def remember(self, *args, **kwargs):
            init(self, *args, **kwargs)
            made.append(self)
        with monkeypatch.context() as patch:
            patch.setattr(GeneratePayload, '__init__', remember)
            patch.setattr(GeneratePayload, 'check_existing_relations', lambda self, *a, **k: None)
            try:
                main._CATALOG_PREPARE_MAP[catalog][1]().export(answers, get_url('mardi', 'uri'))
            except ValueError as error:
                result['export_error'] = f'{type(error).__name__}: {error.args[:2]}'
        if not made:
            raise RuntimeError('no payload built')
        payload = made[0]
        dictionary = payload.state.dictionary
        relations = [key for key in dictionary if key.startswith('RELATION')]
        extra = {}
        if CASES.index((name, qid)) % 10 == 0:
            for key in relations[::5][:40]:
                for how, entry in altered(dictionary[key]):
                    new_key = f'RELATION{900000 + len(extra)}'
                    dictionary[new_key] = entry
                    extra[new_key] = (key, how)
        keys = [key for key in dictionary if key.startswith('RELATION')]

        # Today: SPARQL for what it can express, the API for math, the rest new
        start = time.monotonic()
        sparql = {}
        for query in payload.build_relation_check_queries():
            bindings = query_sparql(query, get_url('mardi', 'sparql'), strict=True,
                                    waits=EXPORT_RETRY_WAITS, deadline=time.monotonic() + 120)
            if not bindings:
                raise PortalUnavailable('SPARQL failed')
            sparql.update({k: v.get('value', 'false') for k, v in bindings[0].items()})
            time.sleep(0.2)
        math = payload.check_math_relations_via_api(get_url('mardi', 'api'), time.monotonic() + 120)
        result['sparql_seconds'] = round(time.monotonic() - start, 2)
        today = {}
        for index, key in enumerate(keys):
            today[key] = math.get(key) or sparql.get(f'RELATION{index}', 'false')

        # The claims
        start = time.monotonic()
        payload._claims = {}
        subjects = sorted({s for s in (payload._resolve_item_reference(dictionary[k]['url'].split('/')[-2])
                                       for k in keys) if isinstance(s, str) and QID_RE.match(s)})
        claims = payload._fetch_claims(subjects, get_url('mardi', 'api'), time.monotonic() + 120, 'statements')
        claims_today = {key: exists_in_claims(payload, dictionary[key], claims) for key in keys}
        result['api_seconds'] = round(time.monotonic() - start, 2)
        result['subjects'] = len(subjects)

        differences = []
        counts = {'true': 0, 'false': 0}
        for key in keys:
            counts[today[key]] = counts.get(today[key], 0) + 1
            if today[key] != claims_today[key]:
                differences.append({'key': key, 'sparql': today[key], 'claims': claims_today[key],
                                    'altered': extra.get(key), **describe(payload, dictionary[key])})
        result.update({'relations': len(relations), 'altered': len(extra), 'counts': counts,
                       'differences': differences})
    except Exception as error:  # noqa: BLE001
        result['error'] = f'{type(error).__name__}: {error}'
        result['traceback'] = traceback.format_exc()[-3000:]
    result['seconds'] = round(time.monotonic() - started, 1)
    with open(path, 'w') as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False, default=str)
    log(f"{len(os.listdir(OUT)):5}/{len(CASES)} {name:14} {qid:11} relations {result.get('relations', '-'):>5} "
        f"altered {result.get('altered', '-'):>4} differences {len(result.get('differences', [])):>3} "
        f"sparql {result.get('sparql_seconds', '-'):>6} api {result.get('api_seconds', '-'):>5}"
        f"{'  ERROR ' + result['error'][:80] if 'error' in result else ''}")
    time.sleep(PAUSE)
