'''DOIs go to the MaRDI Portal in uppercase, in every statement and qualifier (#217).

The answers keep what the user typed or a source returned; the payload writes
the DOI as the portal does.  A DOI the portal has in lowercase is the same DOI:
no second statement next to it.  Other identifiers keep their case.
'''
import pytest

from MaRDMO.core.config import get_properties
from MaRDMO.export.payload import GeneratePayload

API = 'https://portal.example.org/w/api.php'
DOI, MORWIKI, USES = get_properties()['DOI'], get_properties()['MORwiki ID'], 'P1'
NEW, EXISTING = 'Item0000000001', 'Item0000000002'


@pytest.fixture
def payload(monkeypatch):
    payload = GeneratePayload(url='https://portal.example.org', dependency={},
                              wikibase={'properties': {'DOI': DOI, 'MORwiki ID': MORWIKI}})
    payload.state.dictionary = {
        NEW: {'id': '', 'label': 'New', 'description': 'a new item', 'statements': []},
        EXISTING: {'id': 'Q1', 'label': 'Software', 'description': 'on the portal'},
    }
    monkeypatch.setattr(payload, '_fetch_claims', lambda qids, api_url, deadline, what: payload._claims)
    monkeypatch.setattr(payload, 'merge_qualifiers', lambda *args: None)
    monkeypatch.setattr(payload, 'check_symbols', lambda *args: None)
    return payload


def written(payload, subject=NEW):
    '''The values of the statements and qualifiers *payload* writes for *subject* (new item).'''
    statements = payload.state.dictionary[subject]['statements']
    return [s[2] for s in statements], [q['value']['content'] for s in statements for q in s[3]]


def test_a_doi_statement_is_in_uppercase(payload):
    payload.add_answer(DOI, ['10.5281/zenodo.4011112', 'external-id'], subject=NEW)
    assert written(payload) == (['10.5281/ZENODO.4011112'], [])


def test_a_doi_qualifier_is_in_uppercase(payload):
    payload.add_answer(USES, ['Q5', 'wikibase-item'], subject=NEW,
                       qualifier=payload.add_qualifier(DOI, 'external-id', '10.5281/zenodo.4011114'))
    assert written(payload) == (['Q5'], ['10.5281/ZENODO.4011114'])


def test_other_identifiers_keep_their_case(payload):
    payload.add_answer(MORWIKI, ['Battery_pack', 'external-id'], subject=NEW)
    assert written(payload) == (['Battery_pack'], [])


@pytest.mark.parametrize('on_portal, exists', [('10.5281/zenodo.4011112', 'true'),
                                               ('10.5281/ZENODO.4011112', 'true'),
                                               ('10.5281/zenodo.4011113', 'false')])
def test_a_doi_the_portal_has_in_lowercase_is_not_written_again(payload, on_portal, exists):
    payload.add_answer(DOI, ['10.5281/zenodo.4011112', 'external-id'], subject=EXISTING)
    key = f'RELATION{payload.state.counter - 1}'
    payload._claims = {'Q1': {DOI: [{'id': 'Q1$a', 'mainsnak': {'property': DOI,
                                                                'datavalue': {'value': on_portal}}}]}}
    payload.check_existing_relations(API)
    assert payload.state.dictionary[key]['exists'] == exists


def test_another_identifier_is_compared_with_its_case(payload):
    payload.add_answer(MORWIKI, ['Battery_pack', 'external-id'], subject=EXISTING)
    key = f'RELATION{payload.state.counter - 1}'
    payload._claims = {'Q1': {MORWIKI: [{'id': 'Q1$a', 'mainsnak': {'property': MORWIKI,
                                                                    'datavalue': {'value': 'battery_pack'}}}]}}
    payload.check_existing_relations(API)
    assert payload.state.dictionary[key]['exists'] == 'false'
