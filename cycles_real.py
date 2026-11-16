"""Real relation graphs of the MaRDI Portal as new items, for the cycle breaking of the export (#164).

Run with pytest in the plugin's test environment, like duplicates_dois.py:

    cd ~/Work/MaRDMO-Plugin
    QUESTIONNAIRE=~/Work/MaRDMO-Questionnaire/catalog \\
        pytest dev-tests/cycles_real.py --force-enable-socket -p no:cacheprovider -q -s

Per item of items.json (lists ITEMS, default model,algorithm,workflow): a
project in the test database (TEMP title, gone with the test database) with
the item selected as in the interview, so MaRDMO fills it and its related
items from the portal; its export payload, without the export's checks
against the portal (read-only: only the hydration asks the portal, with a
pause before every request; nothing is posted).  Then every item is made
new, as if a user documented all of it from scratch: its statements on the
portal become statements of its creation.  That is the relation graph the
export orders and whose cycles it breaks.

Writes
- results/cycles/<list>-<QID>.xml: the project (RDMO XML, for runs by hand);
- ../tests/data/cycles/<list>-<QID>.json: the graph, only what the ordering
  sees (per item its statements that refer to other items: property, the
  item of the value, the items of the qualifiers), for
  tests/unit/test_cycles_real.py;
and prints per item: items, references, cycles, statements added afterwards,
time of the ordering.

Environment: ITEMS (comma-separated lists of items.json), ONLY (QIDs), LIMIT.
"""
import json
import os
import re
import time
from pathlib import Path

import pytest
from django.contrib.sites.models import Site
from rdmo.core.exports import prettify_xml
from rdmo.projects.models import Project
from rdmo.projects.renderers import XMLRenderer
from rdmo.projects.serializers.export import ProjectSerializer
from rdmo.questions.models import Catalog as RDMOCatalog

from MaRDMO import main
from MaRDMO.getters import get_url
from MaRDMO.helpers import cycle_groups
from MaRDMO.payload import GeneratePayload
from MaRDMO.queries import portal_labels
from tests.conftest import questionnaire  # noqa: F401
from tests.db.conftest import django_db_setup  # noqa: F401
from tools.synthetic.catalog import Catalog
from tools.synthetic.writer import SENT, Documentation, Portal, polite

HERE = Path(__file__).parent
OUT = HERE / 'results' / 'cycles'
GRAPHS = HERE.parent / 'tests' / 'data' / 'cycles'
CATALOGS = {  # list of items.json: (catalog, section, tab)
    'model': ('mardmo-model-catalog', 'model', 'MM1'),
    'algorithm': ('mardmo-algorithm-catalog', 'algorithm', 'A1'),
    'workflow': ('mardmo-interdisciplinary-workflow-catalog', 'workflow', 'WF1'),
}
KEY = re.compile(r'^Item\d{10}$')
ITEMS = json.loads((HERE / 'items.json').read_text(encoding='utf-8'))
LISTS = os.environ.get('ITEMS', 'model,algorithm,workflow').split(',')
ONLY = set(filter(None, os.environ.get('ONLY', '').split(',')))
LIMIT = int(os.environ.get('LIMIT', 0)) or None
CASES = [(kind, qid) for kind in LISTS for qid in ITEMS[kind][:LIMIT] if not ONLY or qid in ONLY]


def graph(payload):
    '''Every item of *payload* as a new item: ``{key: [[property, value item, [qualifier items]], ...]}``.

    The statements of a portal item are its RELATION entries (their URL names
    the item); only statements that refer to items count for the ordering.
    '''
    statements = {key: [list(st) for st in entry.get('statements', [])]
                  for key, entry in payload.items() if key.startswith('Item')}
    for key, entry in payload.items():
        if key.startswith('RELATION'):
            subject = entry['url'].split('/items/')[1].split('/')[0]
            st = entry['payload']['statement']
            if subject in statements:
                statements[subject].append([st['property']['id'], st['property']['data_type'],
                                            st['value'].get('content'), st.get('qualifiers', [])])
    found = {}
    for key, sts in statements.items():
        kept = []
        for st in sts:
            value = st[2] if isinstance(st[2], str) and KEY.match(st[2]) else None
            qualifiers = [q['value']['content'] for q in (st[3] if len(st) > 3 else [])
                          if isinstance(q['value'].get('content'), str) and KEY.match(q['value']['content'])]
            if value or qualifiers:
                kept.append([st[0], value, qualifiers])
        found[key] = kept
    return found


@pytest.mark.parametrize('kind,qid', CASES)
def test_real_graph(kind, qid, db, monkeypatch, django_db_setup):  # noqa: F811
    catalog_name, section, tab = CATALOGS[kind]
    polite(monkeypatch)
    SENT.clear()
    label = (portal_labels([qid]) or {}).get(qid, ('', ''))[0]
    assert label, f'{qid}: no label on the portal'
    project = Project.objects.create(title=f'TEMP cycles {kind} {qid}', site=Site.objects.get_current(),
                                     catalog=RDMOCatalog.objects.get(uri__endswith=catalog_name))
    doc = Documentation(project, Catalog.read(os.environ['QUESTIONNAIRE'], catalog_name))
    try:
        doc.tab(section, tab, Portal(qid, label))
    except AssertionError as error:
        # E.g. a Wikidata import without the class of the section: the dropdown offers its Wikidata twin
        pytest.skip(f'{qid} {label}: not offered by the dropdown ({str(error)[:120]})')
    hydration = len(SENT)

    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, _ = provider.get_post_data()
    _, prepare_class, _ = main._CATALOG_PREPARE_MAP[catalog_name]
    monkeypatch.setattr(GeneratePayload, 'final_checks', lambda self, api_url: None)
    payload, _ = prepare_class().export(answers, get_url('mardi', 'uri'))

    statements = graph(payload)
    labels = {key: payload[key].get('label', '') for key in statements}
    name = f'{kind}-{qid}'
    OUT.mkdir(parents=True, exist_ok=True)
    GRAPHS.mkdir(parents=True, exist_ok=True)
    xml = prettify_xml(XMLRenderer().render(ProjectSerializer(project).data))
    (OUT / f'{name}.xml').write_text(xml.decode() if isinstance(xml, bytes) else xml, encoding='utf-8')
    (GRAPHS / f'{name}.json').write_text(json.dumps(
        {'source': f'{kind} {qid} {label}', 'labels': labels, 'statements': statements},
        indent=1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')

    # The ordering on it, as tests/unit/test_cycles_real.py does
    from tests.unit.test_cycles import build, postponed   # pylint: disable=import-outside-toplevel
    items = {key: [[prop, 'wikibase-item', value or 'Q1', [
        {'property': {'id': 'P0', 'data_type': 'wikibase-item'}, 'value': {'type': 'value', 'content': ref}}
        for ref in refs]] for prop, value, refs in sts] for key, sts in statements.items()}
    start = time.perf_counter()
    ordered = build(items)
    ordered.order_items()
    elapsed = time.perf_counter() - start
    references = sum(len(sts) for sts in statements.values())
    groups = cycle_groups({key: {ref for prop, value, refs in sts for ref in [value, *refs] if ref} - {key}
                           for key, sts in statements.items()})
    print(f'\n{name} ({label}): {len(statements)} items, {references} references, {len(groups)} cycles '
          f'(largest {max(map(len, groups), default=0)}), {len(postponed(ordered))} statements afterwards, '
          f'{elapsed * 1000:.0f} ms; {hydration} requests for the hydration')
