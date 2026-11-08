'''What an export would send to the MaRDI Portal, compared with stored files (golden tests).

For each project, the check messages, the payload and the items written,
as the export hands them to the upload (main._submit_catalog), must equal
tests/data/golden/<project>.json; nothing is sent.  The order of the writes
is checked to put every item after the items it needs; items that do not
need each other come in any order (topological_order).  The
projects are documentations made with MaRDMO (tests/data/projects, RDMO
project exports) and the portal items of tests/db/test_hydration.py,
exported unchanged.  The portal's answers are recorded (tests/recordings.py).

After an intended change of the export, write the golden files again and
review their diff:

    GOLDEN=1 pytest tests/db/test_export.py
'''
import json
import os
from pathlib import Path

import pytest
from rdmo.core.xml import get_ns_map, get_uri, read_xml_file
from rdmo.projects.imports import RDMOXMLImport

from MaRDMO import main
from MaRDMO.checks import Checks
from MaRDMO.getters import get_url
from MaRDMO.helpers import is_cyclic, topological_order
from tests.db.conftest import select
from tests.db.test_hydration import CASES

DATA = Path(__file__).parents[1] / 'data'
DOCUMENTATIONS = sorted(path.stem for path in (DATA / 'projects').glob('*.xml'))


def imported(project, name):
    '''The RDMO project export tests/data/projects/<name>.xml as a project of the test database.'''
    root = read_xml_file(DATA / 'projects' / f'{name}.xml')
    importer = RDMOXMLImport('xml', 'xml', 'rdmo.projects.imports.RDMOXMLImport')
    importer.ns_map = get_ns_map(root)
    documentation = project(get_uri(root.find('catalog'), importer.ns_map).rsplit('/', 1)[1])
    missing = set()
    for node in root.find('values').findall('value'):
        value = importer.get_value(node)
        if value.attribute is None:
            missing.add(get_uri(node.find('attribute'), importer.ns_map))
            continue
        value.project = documentation
        value.save()
    assert not missing, f'attributes not in the questionnaire: {sorted(missing)}'
    return documentation


def export(project):
    '''Check messages, payload and write order, as the export would hand them to the upload.'''
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, _ = provider.get_post_data()
    catalog = str(project.catalog)
    _, prepare_class, check_method = main._CATALOG_PREPARE_MAP[catalog.rsplit('/', 1)[1]]
    messages = getattr(Checks(), check_method)(project=project, data=answers, catalog=catalog)
    if messages:
        return {'messages': [str(message) for message in messages]}
    payload, dependency = prepare_class().export(answers, get_url('mardi', 'uri'))
    assert not is_cyclic(dependency)
    order = topological_order(dependency)
    position = {item: index for index, item in enumerate(order)}
    assert all(position[needed] < position[item] for item, needs in dependency.items() for needed in needs)
    return json.loads(json.dumps({'messages': [], 'payload': payload, 'written': sorted(order)}, default=str))


def leaves(data, path=''):
    '''{path: value} of every value in nested dicts and lists.'''
    if isinstance(data, dict):
        return {key: value for name, child in data.items() for key, value in leaves(child, f'{path}/{name}').items()}
    if isinstance(data, list):
        return {key: value for index, child in enumerate(data)
                for key, value in leaves(child, f'{path}[{index}]').items()}
    return {path: data}


def compare(name, result):
    path = DATA / 'golden' / f'{name}.json'
    if os.environ.get('GOLDEN') == '1':
        path.write_text(json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    assert path.exists(), f'{path.name} missing: GOLDEN=1 pytest tests/db/test_export.py'
    expected, found = leaves(json.loads(path.read_text(encoding='utf-8'))), leaves(result)
    changed = sorted(key for key in expected.keys() | found.keys() if expected.get(key) != found.get(key))
    assert not changed, f'{len(changed)} values differ from {path.name}:\n' + '\n'.join(
        f'  {key}: {expected.get(key)!r} -> {found.get(key)!r}' for key in changed[:15])


@pytest.mark.parametrize('name', DOCUMENTATIONS)
def test_documentation_exports_as_stored(name, project, portal):
    portal(f'export_{name}')
    compare(name, export(imported(project, name)))


@pytest.mark.parametrize('name', sorted(CASES))
def test_unchanged_portal_item_exports_as_stored(name, project, portal):
    portal(name, f'export_portal_{name}')
    catalog, qkey, page, external_id, label, description = CASES[name]
    selected = project(catalog)
    select(selected, qkey, page, external_id, f'{label} ({description}) [{external_id.split(":")[0]}]')
    compare(f'portal_{name}', export(selected))
