'''What the export sends (OauthProviderMixin._post_data) and lists afterwards (collect_statements).'''
import pytest

import MaRDMO.oauth2 as oauth2
from MaRDMO.helpers import collect_statements

URL = 'https://portal.example.org/w/rest.php/wikibase/v1/entities/items/Q1/statements'
ASSUMES = {'property': {'id': 'P20', 'data_type': 'wikibase-item'}, 'value': {'type': 'value', 'content': 'Q30'}}
ROLE = {'property': {'id': 'P10', 'data_type': 'wikibase-item'}, 'value': {'type': 'value', 'content': 'Q9'}}


def relation(exists, **extra):
    return {
        'id': '',
        'url': URL,
        'exists': exists,
        'payload': {'statement': {
            'property': {'id': 'P1', 'data_type': 'wikibase-item'},
            'value': {'type': 'value', 'content': 'Q2'},
            'qualifiers': [ROLE, ASSUMES],
        }},
        **extra,
    }


class Session:
    '''Records requests and answers like the REST API.'''

    def __init__(self):
        self.requests = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.requests.append((method, url, json))
        return Response()


class Response:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {'id': 'Q1$new'}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(oauth2.time, 'sleep', lambda seconds: None)
    provider = oauth2.OauthProviderMixin()
    provider._session = Session()
    return provider


def test_new_statement_is_posted(provider):
    jsons = provider._post_data('RELATION0', {'RELATION0': relation('false')}, 'token')
    [(method, url, body)] = provider._session.requests
    assert (method, url) == ('post', URL)
    assert body == jsons['RELATION0']['payload']
    assert jsons['RELATION0']['id'] == 'Q1$new'


def test_ids_of_the_project_are_not_sent_with_a_new_item(provider):
    '''user_ids are for writing the new ID back into the project (helpers.replace_ids).'''
    item = {'id': '', 'url': 'https://portal.example.org/w/rest.php/wikibase/v1/entities/items',
            'payload': {'item': {'labels': {'en': 'alpha'}}}, 'user_ids': ['user:1']}
    provider._post_data('Item0000000000', {'Item0000000000': item}, 'token')
    [(_, _, body)] = provider._session.requests
    assert body == {'item': {'labels': {'en': 'alpha'}}}


def test_existing_statement_is_not_sent(provider):
    provider._post_data('RELATION0', {'RELATION0': relation('true')}, 'token')
    assert provider._session.requests == []


def test_missing_qualifiers_are_patched_into_the_statement(provider):
    entry = relation('partial', statement_id='Q1$abc', add_qualifiers=[ASSUMES])
    provider._post_data('RELATION0', {'RELATION0': entry}, 'token')
    [(method, url, body)] = provider._session.requests
    assert (method, url) == ('patch', f'{URL}/Q1$abc')
    assert body == {'patch': [{'op': 'add', 'path': '/qualifiers/-',
                               'value': {'property': {'id': 'P20'}, 'value': ASSUMES['value']}}]}


# --- results page

NAMES = {'P1': 'contains', 'P10': 'object has role', 'P20': 'assumes'}


def test_statement_with_added_qualifiers_lists_only_those():
    jsons = {'RELATION0': relation('partial', id='Q1$abc', statement_id='Q1$abc', add_qualifiers=[ASSUMES])}
    [statement] = collect_statements({}, jsons, pid_to_name=NAMES)
    assert statement[2] == 'contains'
    assert statement[5] == [{'prop': 'assumes', 'obj': 'Q30', 'obj_qid': 'Q30'}]
    assert statement[8] is True


def test_new_statement_lists_all_qualifiers():
    jsons = {'RELATION0': relation('false', id='Q1$new')}
    [statement] = collect_statements({}, jsons, pid_to_name=NAMES)
    assert [q['prop'] for q in statement[5]] == ['object has role', 'assumes']
    assert statement[8] is False


def test_existing_and_unsent_statements_are_not_listed():
    jsons = {'RELATION0': relation('true', id='Q1$old'), 'RELATION1': relation('false')}
    assert collect_statements({}, jsons) == []


def test_statements_of_new_items_are_listed():
    init = {'Item0000000001': {'id': ''}, 'Item0000000002': {'id': 'Q2'}}
    jsons = {
        'Item0000000001': {'id': 'Q5', 'label': 'New Model', 'statements': [['P1', 'wikibase-item', 'Q2']]},
        'Item0000000002': {'id': 'Q2', 'label': 'Existing', 'statements': [['P1', 'wikibase-item', 'Q3']]},
    }
    [statement] = collect_statements(init, jsons, pid_to_name=NAMES)
    assert statement[:5] == ['New Model', 'Q5', 'contains', 'Existing', 'Q2']
