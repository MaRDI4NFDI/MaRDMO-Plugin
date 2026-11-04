'''GeneratePayload.merge_qualifiers: new statements versus qualifiers for existing ones.

The portal's claims are put into the payload's claims cache, so no request
is made.  Statements are built with add_answer/add_qualifier as the workers
do; "exists" is set as the SPARQL existence check would.
'''
import pytest

from MaRDMO.payload import GeneratePayload

CONTAINS, USES, ROLE, SYMBOL, PLATFORM, ASSUMES = 'P1', 'P2', 'P10', 'P11', 'P12', 'P20'
SUBJECT, OBJECT = 'Item0000000001', 'Item0000000002'


def qualifier(prop, value):
    return {'property': {'id': prop, 'data_type': 'wikibase-item'}, 'value': {'type': 'value', 'content': value}}


def claim(statement_id, value, **qualifiers):
    '''A portal claim of SUBJECT (Q1) with item value *value* and item qualifiers.'''
    return {
        'id': statement_id,
        'mainsnak': {'datavalue': {'value': {'id': value}}},
        'qualifiers': {
            prop: [{'datavalue': {'value': {'id': v}}} for v in values]
            for prop, values in qualifiers.items()
        },
    }


@pytest.fixture
def payload():
    payload = GeneratePayload(
        url='https://portal.example.org',
        wikibase={'properties': {'contains': CONTAINS, 'uses': USES, 'object has role': ROLE,
                                 'symbol represents': SYMBOL, 'platform': PLATFORM, 'assumes': ASSUMES}},
        dependency={},
    )
    payload.state.dictionary = {
        SUBJECT: {'id': 'Q1', 'label': 'Model', 'description': 'a model'},
        OBJECT: {'id': 'Q2', 'label': 'Formulation', 'description': 'a formulation'},
    }
    return payload


def relation(payload, *qualifiers, exists='false', value=OBJECT, prop=CONTAINS):
    '''Add a "contains" (or *prop*) statement of SUBJECT; returns its RELATION key.'''
    payload.add_answer(prop, [value, 'wikibase-item'],
                       qualifier=[q for pair in qualifiers for q in payload.add_qualifier(pair[0], 'wikibase-item', pair[1])],
                       subject=SUBJECT)
    key = f'RELATION{payload.state.counter - 1}'
    payload.state.dictionary[key]['exists'] = exists
    return key


def portal(payload, *claims, prop=CONTAINS):
    payload._claims = {'Q1': {prop: list(claims)}}


def test_missing_additive_qualifier_is_added_to_the_statement(payload):
    key = relation(payload, (ROLE, 'Q9'), (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    entry = payload.state.dictionary[key]
    assert entry['exists'] == 'partial'
    assert entry['statement_id'] == 'Q1$a'
    assert entry['add_qualifiers'] == [qualifier(ASSUMES, 'Q30')]


def test_statement_with_all_qualifiers_exists(payload):
    key = relation(payload, (ROLE, 'Q9'), (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9'], ASSUMES: ['Q30', 'Q31']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'true'


def test_other_role_is_a_statement_of_its_own(payload):
    '''"contains A as initial condition" on the portal, "contains A as boundary condition" added.'''
    key = relation(payload, (ROLE, 'Q8'), (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_no_role_is_a_meaning_too(payload):
    '''A plain "contains A" next to "contains A as initial condition" is a statement of its own.'''
    with_role = relation(payload, (ROLE, 'Q9'), exists='true')
    plain = relation(payload, (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[with_role]['exists'] == 'true'
    assert payload.state.dictionary[plain]['exists'] == 'false'


def test_existing_statement_found_by_sparql_with_other_meaning_is_new(payload):
    '''The SPARQL check does not look at missing qualifiers: a plain "contains" matches one with a role.'''
    key = relation(payload, exists='true')
    relation(payload, (ROLE, 'Q9'), exists='true')
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_statements_without_meaning_qualifier_get_the_additions(payload):
    key = relation(payload, (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2'))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    entry = payload.state.dictionary[key]
    assert (entry['exists'], entry['statement_id']) == ('partial', 'Q1$a')
    assert entry['add_qualifiers'] == [qualifier(ASSUMES, 'Q30')]


def test_a_qualifier_is_planned_only_once(payload):
    '''Two entries adding the same qualifier to one statement: the second one has nothing left to add.'''
    first = relation(payload, (ASSUMES, 'Q30'))
    second = relation(payload, (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2'))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[first]['exists'] == 'partial'
    assert payload.state.dictionary[second]['exists'] == 'true'


def test_statement_with_fewest_missing_qualifiers_is_chosen(payload):
    key = relation(payload, (ASSUMES, 'Q30'), (ASSUMES, 'Q31'))
    portal(payload, claim('Q1$a', 'Q2'), claim('Q1$b', 'Q2', **{ASSUMES: ['Q31']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    entry = payload.state.dictionary[key]
    assert (entry['statement_id'], entry['add_qualifiers']) == ('Q1$b', [qualifier(ASSUMES, 'Q30')])


def test_other_value_is_a_new_statement(payload):
    key = relation(payload, (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q3'))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_new_object_item_is_not_checked(payload):
    '''An object created in this export cannot be in a portal statement; nothing is fetched.'''
    payload.state.dictionary[OBJECT]['id'] = ''
    key = relation(payload, (ASSUMES, 'Q30'))
    payload._fetch_claims = pytest.fail
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_role_referring_to_a_new_item_is_a_new_statement(payload):
    payload.state.dictionary['Item0000000003'] = {'id': '', 'label': 'Role', 'description': 'new'}
    key = relation(payload, (ROLE, 'Item0000000003'), (ASSUMES, 'Q30'))
    payload._fetch_claims = pytest.fail
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_claims_that_cannot_be_fetched_stop_the_export(payload, monkeypatch):
    import requests

    import MaRDMO.payload as module

    def unreachable(*args, **kwargs):
        raise requests.exceptions.ConnectionError('offline')

    monkeypatch.setattr(module, 'request_with_retry', unreachable)
    relation(payload, (ASSUMES, 'Q30'))
    with pytest.raises(ValueError, match='Nothing was exported'):
        payload.merge_qualifiers('https://portal.example.org/w/api.php')



# --- plain statements found by the SPARQL check (it also finds statements with a qualifier)

def test_only_a_plain_statement_against_one_with_a_role(payload):
    '''The export holds only "contains A"; the portal has "contains A as initial condition".'''
    key = relation(payload, exists='true')
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_plain_statement_that_is_on_the_portal_stays(payload):
    key = relation(payload, exists='true')
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9']}), claim('Q1$b', 'Q2', **{ASSUMES: ['Q30']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'true'


def test_statement_with_a_role_against_a_plain_one_is_new(payload):
    '''The SPARQL check asks for the role, so it does not find the plain statement.'''
    key = relation(payload, (ROLE, 'Q9'))
    portal(payload, claim('Q1$a', 'Q2'))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_uses_without_platform_against_one_with_a_platform(payload):
    key = relation(payload, exists='true', prop=USES)
    portal(payload, claim('Q1$a', 'Q2', **{PLATFORM: ['Q40']}), prop=USES)
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_uses_with_another_platform_is_new(payload):
    key = relation(payload, (PLATFORM, 'Q41'), prop=USES)
    portal(payload, claim('Q1$a', 'Q2', **{PLATFORM: ['Q40']}), prop=USES)
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_uses_with_the_same_platform_stays(payload):
    key = relation(payload, (PLATFORM, 'Q40'), exists='true', prop=USES)
    portal(payload, claim('Q1$a', 'Q2', **{PLATFORM: ['Q40']}), prop=USES)
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'true'


def test_found_statements_of_other_properties_are_not_fetched(payload):
    '''Properties without meaning qualifiers keep the SPARQL result; no claims are fetched.'''
    key = relation(payload, exists='true', prop='P3')
    payload._fetch_claims = pytest.fail
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'true'


# --- portal statements with several roles (MaRDMO writes one role per statement)

def test_one_of_the_roles_of_a_statement_is_that_statement(payload):
    key = relation(payload, (ROLE, 'Q9'), exists='true')
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9', 'Q8']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'true'


def test_both_roles_imported_as_two_relations_are_that_statement(payload):
    first = relation(payload, (ROLE, 'Q9'), exists='true')
    second = relation(payload, (ROLE, 'Q8'), exists='true')
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9', 'Q8']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[first]['exists'] == payload.state.dictionary[second]['exists'] == 'true'


def test_additions_go_to_the_statement_with_several_roles(payload):
    key = relation(payload, (ROLE, 'Q9'), (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9', 'Q8']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    entry = payload.state.dictionary[key]
    assert (entry['exists'], entry['statement_id'], entry['add_qualifiers']) == (
        'partial', 'Q1$a', [qualifier(ASSUMES, 'Q30')])


def test_statement_with_exactly_these_roles_is_preferred(payload):
    key = relation(payload, (ROLE, 'Q9'), (ASSUMES, 'Q30'))
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9', 'Q8']}), claim('Q1$b', 'Q2', **{ROLE: ['Q9']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['statement_id'] == 'Q1$b'


def test_more_roles_than_the_statement_is_new(payload):
    key = relation(payload, (ROLE, 'Q9'), (ROLE, 'Q8'), exists='true')
    portal(payload, claim('Q1$a', 'Q2', **{ROLE: ['Q9']}))
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_one_of_two_platforms_is_another_usage(payload):
    '''Software and hardware describe one usage; parameters belong to it.'''
    key = relation(payload, (PLATFORM, 'Q40'), exists='true', prop=USES)
    portal(payload, claim('Q1$a', 'Q2', **{PLATFORM: ['Q40', 'Q41']}), prop=USES)
    payload.merge_qualifiers('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


@pytest.mark.parametrize('entry, portal_statement, same', [
    (set(), set(), True),
    (set(), {(ROLE, 'Q9')}, False),                                  # no role matches no role only
    ({(ROLE, 'Q9')}, set(), False),
    ({(ROLE, 'Q9')}, {(ROLE, 'Q9'), (ROLE, 'Q8')}, True),
    ({(ROLE, 'Q7')}, {(ROLE, 'Q9'), (ROLE, 'Q8')}, False),
    ({(ROLE, 'Q9'), (SYMBOL, 'Q5')}, {(ROLE, 'Q9'), (ROLE, 'Q8'), (SYMBOL, 'Q5')}, True),
    ({(ROLE, 'Q9'), (SYMBOL, 'Q5')}, {(ROLE, 'Q9'), (SYMBOL, 'Q5'), (SYMBOL, 'Q6')}, False),
    ({(PLATFORM, 'Q40')}, {(PLATFORM, 'Q40'), (PLATFORM, 'Q41')}, False),
])
def test_same_meaning(entry, portal_statement, same):
    assert GeneratePayload._same_meaning(entry, portal_statement, ROLE) is same
