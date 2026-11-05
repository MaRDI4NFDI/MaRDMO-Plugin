'''What the error page of a stopped export says (found with the staging test).

Problems found during the export, after the checks, were all shown as
"Value Error".  Those the user can fix now look like the checks, an
unreachable portal asks to try again, and an internal error says so.
'''
import pytest
import requests

import MaRDMO.payload as payload_module
from MaRDMO.main import export_error_title
from MaRDMO.payload import DocumentationProblem, GeneratePayload, PortalUnavailable


@pytest.mark.parametrize('error, title', [
    (DocumentationProblem('symbol a already stands for Q1'), 'Incomplete or Inconsistent Documentation'),
    (PortalUnavailable('not reachable'), 'MaRDI Portal not reachable'),
    (ValueError('placeholder without item'), 'Export not possible'),
    (KeyError('community'), 'Export not possible'),
])
def test_title(error, title):
    assert str(export_error_title(error)) == title


@pytest.fixture
def payload():
    payload = GeneratePayload(url='https://portal.example.org', dependency={},
                              wikibase={'properties': {'in defining formula': 'P983', 'symbol represents': 'P984',
                                                       'URL': 'P5', 'object has role': 'P560'},
                                        'items': {}, 'relations': {}})
    payload.state.dictionary = {'Item0000000001': {'id': 'Q1', 'label': 'formula', 'description': 'a formula'},
                                'Item0000000002': {'id': 'Q2', 'label': 'quantity', 'description': 'a quantity'}}
    return payload


def test_symbol_for_another_quantity_is_a_documentation_problem(payload):
    payload.add_answer('P983', ['a', 'math'], subject='Item0000000001',
                       qualifier=payload.add_qualifier('P984', 'wikibase-item', 'Item0000000002'))
    payload.state.dictionary['RELATION0']['exists'] = 'false'
    payload._claims = {'Q1': {'P983': [{'id': 'Q1$a', 'mainsnak': {'datavalue': {'value': 'a'}},
                                        'qualifiers': {'P984': [{'datavalue': {'value': {'id': 'Q9'}}}]}}]}}
    with pytest.raises(DocumentationProblem):
        payload.check_symbols('https://portal.example.org/w/api.php')


def test_invalid_url_is_a_documentation_problem(payload):
    payload.add_answer('P5', ['not a url', 'url'], subject='Item0000000001')
    with pytest.raises(DocumentationProblem):
        payload.validate_identifiers()


def test_placeholder_without_item_is_an_internal_error(payload):
    payload.add_answer('P983', ['a', 'math'], subject='Item0000000001',
                       qualifier=payload.add_qualifier('P984', 'wikibase-item', 'Item0000000031'))
    with pytest.raises(ValueError) as error:
        payload.validate_identifiers()
    assert not isinstance(error.value, DocumentationProblem)


def test_unreachable_api_is_portal_unavailable(payload, monkeypatch):
    def unreachable(*args, **kwargs):
        raise requests.exceptions.ConnectionError('offline')

    monkeypatch.setattr(payload_module, 'request_with_retry', unreachable)
    with pytest.raises(PortalUnavailable):
        payload._fetch_claims(['Q1'], 'https://portal.example.org/w/api.php', None, 'formulas')


def test_existing_item_is_a_documentation_problem(payload):
    payload._duplicates = {('formula', 'a formula'): 'Q7'}
    with pytest.raises(DocumentationProblem, match='already exists'):
        payload._check_mardi_and_raise('formula', 'a formula')
