'''Symbols of formulas: one quantity per symbol, symbols without quantity, the portal comparison.

A formula or quantity definition has one symbol table, shared by all of its
formula fields (an equation system in one field, or equivalent formulas in
several): a symbol stands for one quantity in all of them.
'''
import pytest
from django.template.loader import render_to_string

import MaRDMO.model.handlers as handlers
from MaRDMO.checks import Checks
from MaRDMO.models import Relatant
from MaRDMO.model.utils import map_entity_quantity
from MaRDMO.payload import GeneratePayload
from MaRDMO.templatetags.mardmo_tags import element_problems
from MaRDMO.validators import element_symbol_problems

VELOCITY = {'ID': 'mardi:Q10', 'Name': 'velocity', 'Description': 'speed in a direction'}
PRESSURE = {'ID': 'mardi:Q11', 'Name': 'pressure', 'Description': 'force per area'}
RATE = {'ID': 'mardi:Q12', 'Name': 'reaction rate constant', 'Description': 'rate of a reaction'}


def element(symbol, quantity):
    return {'symbol': symbol, 'quantity': quantity}


# --- one symbol, one quantity (within one formula or quantity definition)

def test_symbol_with_two_quantities():
    elements = {0: element('a', VELOCITY), 1: element('b', PRESSURE), 2: element('a', PRESSURE)}
    assert element_symbol_problems(elements) == {0: 'several', 2: 'several'}


def test_symbols_compared_as_exported():
    '''Outer whitespace and line breaks do not make another symbol.'''
    assert element_symbol_problems({0: element('a', VELOCITY), 1: element(' a\n', PRESSURE)}) == {
        0: 'several', 1: 'several'}


def test_several_symbols_for_one_quantity_are_fine():
    elements = {0: element('k_1', RATE), 1: element('k_2', RATE), 2: element('k_3', RATE)}
    assert element_symbol_problems(elements) == {}


def test_same_symbol_and_quantity_twice_is_a_duplicate():
    assert element_symbol_problems({0: element('a', VELOCITY), 1: element('a', dict(VELOCITY))}) == {
        1: 'duplicate'}


def test_own_quantities_are_compared_by_name_and_description():
    own = {'ID': 'not found', 'Name': 'Velocity ', 'Description': 'speed in a direction'}
    other = {'ID': 'not found', 'Name': 'velocity', 'Description': 'another description'}
    assert element_symbol_problems({0: element('a', own), 1: element('a', dict(own, Name='velocity'))}) == {
        1: 'duplicate'}
    assert element_symbol_problems({0: element('a', own), 1: element('a', other)}) == {
        0: 'several', 1: 'several'}


def test_missing_symbol_or_quantity_is_left_to_the_other_checks():
    assert element_symbol_problems({0: element('a', VELOCITY), 1: element('a', None), 2: element('', PRESSURE)}) == {}


def checks_for(page):
    checks = Checks()
    checks._check_element_symbols(page, 'Formula', 'F1')
    return checks.err


def test_check_message_names_the_symbol_once():
    err = checks_for({'element': {0: element('a', VELOCITY), 1: element('a', PRESSURE)}})
    assert len(err) == 1
    assert 'Symbol "a" stands for several quantities' in str(err[0])


def test_symbol_used_in_two_formula_fields_counts_once():
    '''The table is the item's: "a" in an equation system and in an equivalent formula is one symbol.'''
    page = {'Formula': {0: r'\begin{align} a &= b \\ b &= c \end{align}', 1: 'a = c'},
            'element': {0: element('a', VELOCITY), 1: element('b', PRESSURE), 2: element('c', RATE)}}
    assert checks_for(page) == []


# --- preview

def render(elements):
    return render_to_string('MaRDMO/partials/_in_defining_formula.html', {'element': elements})


def test_preview_marks_the_symbols():
    elements = {
        0: {'symbol': 'a', 'quantity': VELOCITY, 'Info': {'Type': 'Quantity', 'Name': 'velocity', 'ID': 'mardi:Q10',
                                                         'Description': 'speed'}},
        1: {'symbol': 'a', 'quantity': PRESSURE, 'Info': {'Type': 'Quantity', 'Name': 'pressure', 'ID': 'mardi:Q11',
                                                         'Description': 'force'}},
        2: {'symbol': 'b'},
    }
    html = render(elements)
    assert html.count('SYMBOL STANDS FOR SEVERAL QUANTITIES') == 2
    assert 'MISSING QUANTITY OR QUANTITY KIND' in html


def test_preview_filter():
    assert element_problems({0: element('a', VELOCITY), 1: element('a', dict(VELOCITY))}) == {
        1: 'SYMBOL APPEARS TWICE WITH THE SAME QUANTITY'}


def test_element_without_quantity_does_not_match_a_page_without_name():
    data = {'formulation': {0: {'element': {0: {'symbol': 'a'}}}},
            'quantity': {0: {'Name': '', 'QorQK': 'Quantity'}}}
    map_entity_quantity(data, 'formulation')
    assert 'Info' not in data['formulation'][0]['element'][0]


# --- import: a symbol without "symbol represents" on the portal

class FormulaData:
    formulas = ['a = b']
    symbols = ['a', 'b']
    contains_quantity = [Relatant.from_triple('', 'No Label Provided!', 'No Description Provided!'),
                         Relatant.from_triple('mardi:Q11', 'pressure', 'force per area')]


def test_symbol_without_quantity_is_written_without_one(monkeypatch):
    written = []
    monkeypatch.setattr(handlers, 'value_editor', lambda project, uri, info: written.append((uri, info)))
    page = {name: {'uri': f'domain/formulation/{name}'} for name in ('Formula', 'Element Symbol', 'Element Quantity')}
    handlers.write_defining_formula(None, page, FormulaData(), 3)
    symbols = [info for uri, info in written if uri.endswith('Element Symbol')]
    quantities = [info for uri, info in written if uri.endswith('Element Quantity')]
    assert [(s['text'], s['set_index']) for s in symbols] == [('a', 0), ('b', 1)]
    assert [(q['external_id'], q['set_index']) for q in quantities] == [('mardi:Q11', 1)]
    assert not any('No Label Provided!' in str(info) for _, info in written)


# --- export: the symbols of the item on the portal

IN_FORMULA, REPRESENTS = 'P983', 'P984'
FORMULA, QUANTITY = 'Item0000000001', 'Item0000000002'


@pytest.fixture
def payload():
    payload = GeneratePayload(
        url='https://portal.example.org', dependency={},
        wikibase={'properties': {'in defining formula': IN_FORMULA, 'symbol represents': REPRESENTS,
                                 'object has role': 'P560', 'platform': 'P143'}, 'items': {}, 'relations': {}},
    )
    payload.state.dictionary = {
        FORMULA: {'id': 'Q1', 'label': 'stationary flow assumption', 'description': 'a formula'},
        QUANTITY: {'id': 'Q2', 'label': 'velocity', 'description': 'speed in a direction'},
    }
    return payload


def symbol(payload, value='a', quantity=QUANTITY):
    payload.add_answer(IN_FORMULA, [value, 'math'], subject=FORMULA,
                       qualifier=payload.add_qualifier(REPRESENTS, 'wikibase-item', quantity))
    key = f'RELATION{payload.state.counter - 1}'
    payload.state.dictionary[key]['exists'] = 'false'    # as the math check finds it
    return key


def portal(payload, *statements):
    '''Statements "in defining formula" of Q1: (statement ID, symbol, [quantities]).'''
    payload._claims = {'Q1': {IN_FORMULA: [
        {'id': sid, 'mainsnak': {'datavalue': {'value': value}},
         'qualifiers': {REPRESENTS: [{'datavalue': {'value': {'id': q}}} for q in quantities]} if quantities else {}}
        for sid, value, quantities in statements
    ]}}


def test_symbol_without_quantity_on_the_portal_is_completed(payload):
    key = symbol(payload)
    portal(payload, ('Q1$a', 'a', []))
    payload.check_symbols('https://portal.example.org/w/api.php')
    entry = payload.state.dictionary[key]
    assert (entry['exists'], entry['statement_id']) == ('partial', 'Q1$a')
    assert entry['add_qualifiers'] == [{'property': {'id': REPRESENTS, 'data_type': 'wikibase-item'},
                                        'value': {'type': 'value', 'content': QUANTITY}}]


def test_symbol_with_another_quantity_on_the_portal_stops_the_export(payload):
    '''A symbol block of a fetched formula deleted and added again with another quantity.'''
    symbol(payload)
    portal(payload, ('Q1$a', 'a', ['Q9']))
    with pytest.raises(ValueError, match='symbol a already stands for Q9') as error:
        payload.check_symbols('https://portal.example.org/w/api.php')
    assert 'stationary flow assumption' in str(error.value)


def test_another_quantity_wins_over_completing(payload):
    '''Completing "a" would leave "a" for two quantities on the portal.'''
    symbol(payload)
    portal(payload, ('Q1$a', 'a', []), ('Q1$b', 'a', ['Q9']))
    with pytest.raises(ValueError):
        payload.check_symbols('https://portal.example.org/w/api.php')


def test_same_quantity_on_the_portal_exists(payload):
    key = symbol(payload)
    portal(payload, ('Q1$a', 'a', []), ('Q1$b', 'a', ['Q2']))
    payload.check_symbols('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'true'


def test_new_symbol_is_a_new_statement(payload):
    key = symbol(payload)
    portal(payload, ('Q1$a', 'b', ['Q9']))
    payload.check_symbols('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_new_quantity_completes_the_symbol(payload):
    '''The quantity is created in this export: its placeholder is replaced before the PATCH.'''
    payload.state.dictionary[QUANTITY]['id'] = ''
    key = symbol(payload)
    portal(payload, ('Q1$a', 'a', []))
    payload.check_symbols('https://portal.example.org/w/api.php')
    entry = payload.state.dictionary[key]
    assert entry['exists'] == 'partial'
    assert entry['add_qualifiers'][0]['value']['content'] == QUANTITY


def test_new_quantity_against_another_quantity_stops_the_export(payload):
    payload.state.dictionary[QUANTITY]['id'] = ''
    symbol(payload)
    portal(payload, ('Q1$a', 'a', ['Q9']))
    with pytest.raises(ValueError):
        payload.check_symbols('https://portal.example.org/w/api.php')


def test_symbols_of_other_items_do_not_count(payload):
    key = symbol(payload)
    payload._claims = {'Q1': {}, 'Q5': {IN_FORMULA: [
        {'id': 'Q5$a', 'mainsnak': {'datavalue': {'value': 'a'}},
         'qualifiers': {REPRESENTS: [{'datavalue': {'value': {'id': 'Q9'}}}]}}]}}
    payload.check_symbols('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


def test_formula_without_qid_is_not_checked(payload):
    key = symbol(payload)
    payload.state.dictionary[FORMULA]['id'] = ''
    payload._fetch_claims = pytest.fail
    payload.check_symbols('https://portal.example.org/w/api.php')
    assert payload.state.dictionary[key]['exists'] == 'false'


# --- export: placeholders without an item

def test_placeholder_without_item_stops_before_posting(payload):
    '''The Taylor-Couette model: "symbol represents" pointed to an item the export did not contain.'''
    payload.add_answer(IN_FORMULA, ['a', 'math'], subject=FORMULA,
                       qualifier=payload.add_qualifier(REPRESENTS, 'wikibase-item', 'Item0000000031'))
    with pytest.raises(ValueError, match='Item0000000031'):
        payload.validate_identifiers()


def test_placeholders_of_the_export_pass(payload):
    symbol(payload)
    payload.validate_identifiers()
