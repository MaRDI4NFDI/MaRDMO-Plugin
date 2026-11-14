'''GeneratePayload.check_existing_relations: which statements of existing items are on the portal (#152).

The portal's claims are answered by a stub of _fetch_claims, so no request
is made.  Every data type MaRDMO writes is decided once found and once new.
'''
import pytest

from MaRDMO.payload import GeneratePayload, PortalUnavailable

API = 'https://portal.example.org/w/api.php'
PROP, QUAL = 'P1', 'P2'
SUBJECT, OBJECT, NEW = 'Item0000000001', 'Item0000000002', 'Item0000000003'


def snak(value):
    return {'datavalue': {'value': value}}


def claim(value, **qualifiers):
    '''A portal claim of PROP with the API value *value* and qualifiers {property: [API values]}.'''
    return {'id': 'Q1$a', 'mainsnak': snak(value),
            'qualifiers': {prop: [snak(v) for v in values] for prop, values in qualifiers.items()}}


@pytest.fixture
def payload(monkeypatch):
    payload = GeneratePayload(url='https://portal.example.org', wikibase={'properties': {}}, dependency={})
    payload.state.dictionary = {
        SUBJECT: {'id': 'Q1', 'label': 'Model', 'description': 'a model'},
        OBJECT: {'id': 'Q2', 'label': 'Task', 'description': 'a task'},
        NEW: {'id': '', 'label': 'New', 'description': 'a new item'},
    }
    payload.fetched = []

    def fetch(qids, api_url, deadline, what):
        payload.fetched.append(list(qids))
        return payload._claims
    monkeypatch.setattr(payload, '_fetch_claims', fetch)
    # no merge and symbol check here: the decision of the existence check alone
    monkeypatch.setattr(payload, 'merge_qualifiers', lambda *args: None)
    monkeypatch.setattr(payload, 'check_symbols', lambda *args: None)
    return payload


def relation(payload, value, data_type, qualifiers=(), subject=SUBJECT):
    '''Add a PROP statement of *subject*; returns its RELATION key.'''
    payload.add_answer(PROP, [value, data_type], subject=subject,
                       qualifier=[q for prop, q_type, q_value in qualifiers
                                  for q in payload.add_qualifier(prop, q_type, q_value)])
    return f'RELATION{payload.state.counter - 1}'


def exists(payload, key, *claims):
    payload._claims = {'Q1': {PROP: list(claims)}}
    payload.check_existing_relations(API)
    return payload.state.dictionary[key]['exists']


TYPES = [  # data type, payload value, the portal's API value, another API value
    ('wikibase-item', OBJECT, {'id': 'Q2'}, {'id': 'Q3'}),
    ('string', 'Navier', 'Navier', 'Stokes'),
    ('external-id', '10.1/x', '10.1/x', '10.1/y'),
    ('url', 'https://example.org', 'https://example.org', 'https://example.com'),
    ('math', r'\frac{a}{b}', r'\frac{a}{b}', r'\frac{b}{a}'),
    ('monolingualtext', {'text': 'Name', 'language': 'en'}, {'text': 'Name', 'language': 'en'},
     {'text': 'Name', 'language': 'de'}),
    ('quantity', {'amount': '+2', 'unit': '1'}, {'amount': '+2', 'unit': '1'}, {'amount': '+3', 'unit': '1'}),
    ('quantity', {'amount': '+2', 'unit': 'https://portal.example.org/entity/Q5'},
     {'amount': '+2', 'unit': 'http://www.wikidata.org/entity/Q5'},
     {'amount': '+2', 'unit': 'https://portal.example.org/entity/Q6'}),
    ('time', {'time': '+2020-00-00T00:00:00Z', 'precision': 9}, {'time': '+2020-00-00T00:00:00Z', 'precision': 9},
     {'time': '+2020-00-00T00:00:00Z', 'precision': 11}),
]
IDS = [f'{t[0]}-{n}' for n, t in enumerate(TYPES)]


@pytest.mark.parametrize('data_type, value, api, other', TYPES, ids=IDS)
def test_statement_with_the_value_exists(payload, data_type, value, api, other):
    key = relation(payload, value, data_type)
    assert exists(payload, key, claim(other), claim(api)) == 'true'


@pytest.mark.parametrize('data_type, value, api, other', TYPES, ids=IDS)
def test_statement_with_another_value_is_new(payload, data_type, value, api, other):
    key = relation(payload, value, data_type)
    assert exists(payload, key, claim(other)) == 'false'


@pytest.mark.parametrize('data_type, value, api, other', TYPES, ids=IDS)
def test_qualifier_of_each_type_is_compared(payload, data_type, value, api, other):
    key = relation(payload, OBJECT, 'wikibase-item', [(QUAL, data_type, value)])
    assert exists(payload, key, claim({'id': 'Q2'}, **{QUAL: [other, api]})) == 'true'
    assert exists(payload, key, claim({'id': 'Q2'}, **{QUAL: [other]})) == 'false'


def test_every_qualifier_must_be_there(payload):
    key = relation(payload, OBJECT, 'wikibase-item', [(QUAL, 'wikibase-item', 'Q8'), ('P3', 'string', 'a')])
    assert exists(payload, key, claim({'id': 'Q2'}, **{QUAL: ['x'], 'P3': ['a']})) == 'false'
    assert exists(payload, key, claim({'id': 'Q2'}, **{QUAL: [{'id': 'Q8'}]})) == 'false'
    assert exists(payload, key, claim({'id': 'Q2'}, **{QUAL: [{'id': 'Q8'}], 'P3': ['a']})) == 'true'


def test_claim_with_more_qualifiers_matches(payload):
    '''merge_qualifiers decides afterwards on the qualifiers that give a statement its meaning.'''
    key = relation(payload, OBJECT, 'wikibase-item')
    assert exists(payload, key, claim({'id': 'Q2'}, **{QUAL: [{'id': 'Q8'}]})) == 'true'


def test_value_and_qualifiers_must_be_in_one_claim(payload):
    key = relation(payload, OBJECT, 'wikibase-item', [(QUAL, 'wikibase-item', 'Q8')])
    assert exists(payload, key, claim({'id': 'Q2'}), claim({'id': 'Q3'}, **{QUAL: [{'id': 'Q8'}]})) == 'false'


def test_other_property_does_not_count(payload):
    key = relation(payload, OBJECT, 'wikibase-item')
    payload._claims = {'Q1': {'P9': [claim({'id': 'Q2'})]}}
    payload.check_existing_relations(API)
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_new_item_as_value_or_qualifier_is_new(payload):
    by_value = relation(payload, NEW, 'wikibase-item')
    by_qualifier = relation(payload, OBJECT, 'wikibase-item', [(QUAL, 'wikibase-item', NEW)])
    payload._claims = {'Q1': {PROP: [claim({'id': ''}), claim({'id': 'Q2'}, **{QUAL: [{'id': ''}]})]}}
    payload.check_existing_relations(API)
    assert payload.state.dictionary[by_value]['exists'] == 'false'
    assert payload.state.dictionary[by_qualifier]['exists'] == 'false'


def test_claims_of_the_existing_subjects_are_fetched_once(payload):
    payload.state.dictionary['Item0000000004'] = {'id': 'Q4', 'label': 'Other', 'description': 'another model'}
    relation(payload, OBJECT, 'wikibase-item')
    relation(payload, 'a', 'string')
    relation(payload, OBJECT, 'wikibase-item', subject='Item0000000004')
    payload._claims = {}
    payload.check_existing_relations(API)
    assert payload.fetched == [['Q1', 'Q4']]


def test_without_relations_nothing_is_fetched(payload):
    payload.check_existing_relations(API)
    assert payload.fetched == []


def test_unreachable_portal_stops_the_export(payload, monkeypatch):
    relation(payload, OBJECT, 'wikibase-item')

    def fail(*args):
        raise PortalUnavailable('not reachable')
    monkeypatch.setattr(payload, '_fetch_claims', fail)
    with pytest.raises(PortalUnavailable):
        payload.check_existing_relations(API)
