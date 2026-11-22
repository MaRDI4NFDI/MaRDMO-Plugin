'''What the checks report for pages of MaRDI Portal items: hints, not problems (#167).

The export creates own items and Wikidata items, so everything the checks
find on their pages prevents it.  A portal item is not created: what it
lacks is a hint, and so is an invalid value it has already (MaRDMO does not
write it); an invalid value the user added is written, so it is a problem.
A broken structure (a relation without type) is a problem everywhere.  The
portal's statements are given here.
'''
import pytest

from MaRDMO.checks import Checks
from MaRDMO.constants import CATALOG_ALGORITHM
from MaRDMO.getters import get_options
from MaRDMO.payload import DocumentationProblem, GeneratePayload, PortalUnavailable
from MaRDMO.problems import Problem, report_lines

PORTAL, OWN, WIKIDATA = 'mardi:Q5', 'user:0b5c1e8a-7d1c-4d7e-9d2a-1f3a6c9e2b10', 'wikidata:Q7'


def software(identifier, **answers):
    return {'software': {0: {'ID': identifier, 'Name': 'NumPy', 'Description': 'Python library', 'Tab': 'S1',
                             **answers}}}


def found(checks, data, method):
    getattr(checks, method)(None, data)
    return [(problem.message, problem.hint) for problem in checks.err]


@pytest.fixture
def claims(monkeypatch):
    '''The portal item Q5 has the (invalid) DOI "not-a-doi" and the amount "+8.5".'''
    asked = []

    def fetch(qids, api_url, deadline, what, cache=None):
        asked.append(list(qids))
        return {'Q5': {'P27': [{'mainsnak': {'datavalue': {'value': 'not-a-doi'}}}],
                       'P1': [{'mainsnak': {'datavalue': {'value': {'amount': '+8.5'}}}}]}}
    monkeypatch.setattr('MaRDMO.checks.base.fetch_claims', fetch)
    return asked


def doi(text):
    return {'reference': {0: [get_options()['DOI'], text]}}


@pytest.mark.parametrize('identifier, hint', [(PORTAL, True), (OWN, False), (WIKIDATA, False)])
def test_what_an_item_lacks_is_a_hint_for_portal_items_only(identifier, hint):
    assert found(Checks(), software(identifier), 'software') == [('Missing Reference', hint)]


def test_an_invalid_value_the_portal_item_has_is_a_hint(claims):
    assert found(Checks(), software(PORTAL, **doi('not-a-doi')), 'software') == [
        ('Invalid DOI: DOI must have the form 10.XXXX/suffix (e.g. 10.1000/xyz123)', True)]
    assert claims == [['Q5']]


def test_an_invalid_value_the_user_added_to_a_portal_item_is_a_problem(claims):
    assert found(Checks(), software(PORTAL, **doi('also-not-a-doi')), 'software') == [
        ('Invalid DOI: DOI must have the form 10.XXXX/suffix (e.g. 10.1000/xyz123)', False)]


def test_an_invalid_value_of_an_own_item_is_a_problem_without_lookup(claims):
    assert found(Checks(), software(OWN, **doi('not-a-doi')), 'software') == [
        ('Invalid DOI: DOI must have the form 10.XXXX/suffix (e.g. 10.1000/xyz123)', False)]
    assert claims == []


def test_amounts_are_compared_as_the_portal_has_them(claims):
    '''The portal has "+8.5", the hardware page "8.5" (no integer): a hint.'''
    checks = Checks()
    checks.hardware(None, {'hardware': {0: {'ID': PORTAL, 'Name': 'cluster', 'Description': 'a cluster', 'Tab': 'HW1',
                                            'nodes': '8.5', 'cpu_entries': [{'id': 'mardi:Q9', 'count': '1',
                                                                             'cores': '4'}]}}})
    assert [(problem.message.split(':')[0], problem.hint) for problem in checks.err] == [
        ('Invalid Number of Compute Nodes', True)]


def test_a_portal_that_does_not_answer_keeps_the_hint_and_the_export_waiting(monkeypatch):
    def fail(*args, **kwargs):
        raise PortalUnavailable('not reachable')
    monkeypatch.setattr('MaRDMO.checks.base.fetch_claims', fail)
    checks = Checks()
    assert found(checks, software(PORTAL, **doi('not-a-doi')), 'software')[0][1] is True
    assert checks.unreachable == 'not reachable'


def test_a_broken_structure_is_a_problem_also_for_portal_items():
    checks = Checks()
    page = checks._page('algorithm', 0, {'ID': PORTAL, 'Name': 'a', 'Tab': 'A1'})
    checks._check_flexible({'RelationA': {0: {'relation': None, 'relatant': 'mardi:Q1'}}}, page, 'RelationA',
                           'Algorithm')
    assert [(problem.message, problem.hint) for problem in checks.err] == [('Missing Relation Type (Algorithm)', False)]


def test_the_name_and_description_of_a_portal_item_are_hints():
    checks = Checks()
    checks.id_name_description(None, {'software': {0: {'ID': PORTAL, 'Name': 'BT', 'Tab': 'S1'}}},
                               CATALOG_ALGORITHM)
    assert [(problem.message, problem.hint) for problem in checks.err] == [('Missing Short Description', True)]


def test_hints_are_not_on_the_error_page():
    hint = Problem('Software', None, 'Missing Reference', hint=True)
    assert report_lines([hint]) == []
    assert report_lines([hint, Problem('Software', None, 'Missing Name')])[1:] == ['Software: Missing Name']


# --- The export -----------------------------------------------------------------------------

@pytest.fixture
def payload():
    payload = GeneratePayload(url='https://portal.example.org', dependency={},
                              wikibase={'properties': {'DOI': 'P27', 'symbol represents': 'P984'},
                                        'items': {}, 'relations': {}})
    payload.state.dictionary = {'Item0000000001': {'id': 'Q5', 'label': 'NumPy', 'description': ''}}
    return payload


def test_the_export_checks_only_the_values_it_writes(payload):
    '''A DOI the portal item has is not written, so it is not checked; one it does not have is.'''
    payload.add_answer('P27', ['not-a-doi', 'external-id'], subject='Item0000000001')
    payload.state.dictionary['RELATION0']['exists'] = 'true'
    payload.validate_identifiers()
    payload.state.dictionary['RELATION0']['exists'] = 'false'
    with pytest.raises(DocumentationProblem):
        payload.validate_identifiers()


def test_a_portal_item_needs_no_description_in_the_export(payload):
    payload.user_items = {'Item0000000001': {'ID': PORTAL, 'Name': 'BT', 'Description': ''},
                          'Item0000000002': {'ID': OWN, 'Name': 'mine', 'Description': ''}}
    assert payload.get_item_key({'ID': PORTAL, 'Name': 'BT', 'Description': ''}, 'object') == 'Item0000000001'
    with pytest.raises(DocumentationProblem):
        payload.get_item_key({'ID': OWN, 'Name': 'mine', 'Description': ''}, 'object')
