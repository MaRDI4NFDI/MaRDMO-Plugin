'''The upload of the stored documentations, against a portal that only hands out IDs (#164).

The export of each documentation (tests/data/projects, as in test_export) is
posted by the real upload (oauth2._background_post) to a fake portal: every
new item gets a QID, every statement an ID, nothing goes over the network.
The fake portal rejects any request with an ``Item<n>`` placeholder left,
as the MaRDI Portal does: every item must be created after the items it
refers to, every statement added afterwards after its item.  And every
statement of the export must arrive.
'''
import json
import re
from collections import Counter
from types import SimpleNamespace

import pytest

from MaRDMO import main
from MaRDMO.catalogs import catalog_of
from MaRDMO.ordering import topological_order
from MaRDMO.store import _progress_store
from tests.db.test_export import DOCUMENTATIONS, imported

PLACEHOLDER = re.compile(r'Item\d{10}')


class Portal:
    '''A requests session for the REST API of a Wikibase that keeps nothing but its answers.'''

    def __init__(self):
        self.items, self.statements, self.patches = [], [], []

    def request(self, method, url, json=None, headers=None, timeout=None):  # noqa: A002 (as requests)
        sent = globals()['json'].dumps([url, json])
        assert not PLACEHOLDER.search(sent), f'placeholder left: {PLACEHOLDER.search(sent).group()} in {sent[:300]}'
        if method == 'patch':
            self.patches.append((url, json))
            answer = {'id': url.rsplit('/', 1)[1]}       # the statement, as the REST API answers
        elif url.endswith('/entities/items'):
            self.items.append(json)
            answer = {'id': f'Q{900000 + len(self.items)}'}
        else:
            self.statements.append((url, json))
            answer = {'id': f'Q1$S{len(self.statements)}'}
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: answer)


def export(project):
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, _ = provider.get_post_data()
    prepare_class = catalog_of(project).prepare_class
    payload, dependency = prepare_class().export(answers, 'https://portal.mardi4nfdi.de')
    return provider, payload, dependency


def references(statement):
    return set(PLACEHOLDER.findall(json.dumps(statement)))


@pytest.mark.parametrize('name', DOCUMENTATIONS)
def test_every_reference_of_a_new_item_is_a_dependency(name, project, portal):
    '''Also those in qualifiers (assumptions, the software of a process step): before #164 they were not.'''
    portal(f'export_{name}')
    _, payload, dependency = export(imported(project, name))
    for key, entry in payload.items():
        if key.startswith('Item') and not entry['id']:
            for statement in entry['statements']:
                assert references(statement) - {key} <= dependency[key], (entry['label'], statement)


@pytest.mark.parametrize('name', DOCUMENTATIONS)
def test_the_upload_writes_everything_in_order(name, project, portal, monkeypatch):
    portal(f'export_{name}')
    provider, payload, dependency = export(imported(project, name))
    payload = json.loads(json.dumps(payload))       # the upload writes the IDs into the first entries
    new = [key for key, entry in payload.items() if key.startswith('Item') and not entry['id']]
    relations = [entry for key, entry in payload.items() if key.startswith('RELATION')]
    expected = Counter(statement[0] for key in new for statement in payload[key]['statements'])
    expected.update(entry['payload']['statement']['property']['id'] for entry in relations
                    if entry['url'].split('/items/')[1].split('/')[0] in new)
    fake = Portal()
    provider._session = fake
    monkeypatch.setattr('MaRDMO.oauth2.time.sleep', lambda seconds: None)
    request = SimpleNamespace(build_absolute_uri=lambda path: path)
    provider._background_post(request, 'token', json.loads(json.dumps(payload)), topological_order(dependency),
                              f'test-{name}', None)

    result = _progress_store[f'test-{name}']
    assert result['phase'] == 'done', result.get('error')
    assert len(fake.items) == len(new) == result['counts']['items_created']
    assert len(fake.statements) == sum(1 for entry in relations if entry.get('exists') == 'false') + sum(
        1 for key, entry in payload.items() if key.startswith('ALIAS'))
    assert len(fake.patches) == sum(1 for entry in relations if entry.get('exists') == 'partial')
    # Every statement of a new item arrives once: in its creation or afterwards
    created = Counter(prop for item in fake.items for prop, statements in item['item']['statements'].items()
                      for _ in statements)
    created.update(url_json[1]['statement']['property']['id'] for url_json in fake.statements
                   if '/statements' in url_json[0] and any(f'/items/Q{900000 + n}/' in url_json[0]
                                                          for n in range(1, len(fake.items) + 1)))
    assert created == expected
    print(f'\n{name}: {len(new)} items, {len(fake.statements)} single statements, {len(fake.patches)} additions')
