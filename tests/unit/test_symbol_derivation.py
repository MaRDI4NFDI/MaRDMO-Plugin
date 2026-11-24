'''Symbols entered once (MaRDMO.model.symbols, #179): TeX as tokens, and the rows a formula gets.'''
import pytest

from MaRDMO.model.symbols import canonical, derive_symbols, occurrences, tokens


@pytest.mark.parametrize('one, other', [
    ('T_{0}', 'T_0'),
    ('A_m', r'A_\text{m}'),
    (r'I_{\mathrm{ion}}', r'I_\text{ion}'),
    (r'C^{\rm{f}}_{\rm{m}}', r'C^\text{f}_\text{m}'),
    (r'V^{\text{f}}_{\text{m}}', r'V_m^{\text f}'),
    (r'\sigma_{\mathrm{eff}}', r'\sigma_{ \text{eff} }'),
    (r'\textbf{y}', r'\mathbf{y}'),
    (r'T_{\text{init}}', r'T_\text{init}'),
])
def test_one_symbol_written_two_ways(one, other):
    assert canonical(one) == canonical(other)


@pytest.mark.parametrize('one, other', [('x', 'x^*'), ('T', "T'"), ('T', 'T_0'), (r'\mathcal{L}', 'L')])
def test_two_symbols(one, other):
    assert canonical(one) != canonical(other)


def test_a_power_is_not_part_of_the_symbol():
    assert [str(token) for token in tokens('x^2 + y^{n+1}')][:4] == ['x', '^', '2', '+']
    assert occurrences('x', 'x^2 + 1') == [0]


def test_every_letter_is_a_symbol_and_words_are_not():
    assert [str(token) for token in tokens(r'bsi \text{if} \begin{cases} a \end{cases}')] == [
        'b', 's', 'i', 'if', r'\begin{cases}', 'a', r'\end{cases}']
    assert occurrences('s', r'\begin{cases} s \end{cases}') == [1]


@pytest.mark.parametrize('tex', [
    r'\frac{dT}{dt} = d \cdot T',                # the differentials are not the quantity d
    r'\frac{d a}{d t} = (a - d) y',
    r'd a = c \, a \, d t + d \cdot W',
    r'\int f \, \mathrm{d}x + d',
])
def test_the_differential_is_not_the_symbol_d(tex):
    last = [index for index, token in enumerate(tokens(tex)) if token == 'd'][-1]
    assert occurrences('d', tex) == [last]


def page(tab, tex=None, rows=()):
    entry = {'Tab': tab, 'element': {index: {'symbol': symbol, 'quantity': {'ID': quantity, 'Name': quantity}}
                                     for index, (symbol, quantity) in enumerate(rows)}}
    if tex is not None:
        entry['Formula'] = {0: tex}
    return entry


def derived(entry):
    return {(element['symbol'], element['quantity']['ID'], element.get('derived'))
            for element in entry['element'].values() if element.get('derived')}


def test_a_symbol_entered_once_comes_to_the_formulas_that_use_it():
    answers = {'formulation': {
        0: page('energy balance', r'C \frac{dT}{dt} = -\beta (T - T_0)', [('T', 'temperature'), ('t', 'time'),
                                                                           ('C', 'capacity'), (r'\beta', 'rate'),
                                                                           ('T_{0}', 'start')]),
        1: page('cooling', r'T(t) = T_0 e^{-\beta t}'),
    }}
    derive_symbols(answers)
    assert derived(answers['formulation'][1]) == {('T', 'temperature', 'energy balance'),
                                                   ('t', 'time', 'energy balance'),
                                                   ('T_{0}', 'start', 'energy balance'),
                                                   (r'\beta', 'rate', 'energy balance')}
    assert 'SymbolsUnknown' not in answers['formulation'][1]          # e^ is the exponential function
    assert derived(answers['formulation'][0]) == set()


def test_a_quantity_definition_defines_symbols_too():
    answers = {'quantity': {0: page('time', r't \equiv t', [('t', 'time')])},
               'formulation': {0: page('decay', r'N(t) = N_0 e^{-t}', [('N', 'number'), ('N_0', 'start')])}}
    derive_symbols(answers)
    assert derived(answers['formulation'][0]) == {('t', 'time', 'time')}


def test_the_own_row_wins_and_the_longest_symbol():
    answers = {'formulation': {
        0: page('a', r'\Delta t + t', [(r'\Delta t', 'duration'), ('t', 'time')]),
        1: page('b', r'\Delta t = t_2 - t_1', [('t', 'moment')]),
    }}
    derive_symbols(answers)
    # \Delta t is one symbol; t has two quantities, but b has its own row
    assert derived(answers['formulation'][1]) == {(r'\Delta t', 'duration', 'a')}
    assert 'SymbolsAmbiguous' not in answers['formulation'][1]


def test_a_symbol_for_several_quantities_needs_a_row():
    answers = {'formulation': {
        0: page('general', 'h = H - H_b', [('h', 'hormone excess'), ('H', 'hormone'), ('H_b', 'basal')]),
        1: page('insulin', 'h = H - H_b', [('h', 'insulin excess')]),
        2: page('other', r'\frac{dh}{dt} = -h'),
    }}
    derive_symbols(answers)
    assert answers['formulation'][2]['SymbolsAmbiguous'] == {'h': ['general', 'insulin']}
    assert all(symbol != 'h' for symbol, _, _ in derived(answers['formulation'][2]))


def test_letters_no_table_defines():
    answers = {'formulation': {0: page('a', r'\frac{dx}{dt} = \Delta x + \pi \alpha x', [('x', 'position')])}}
    derive_symbols(answers)
    # d is the differential, \Delta the operator, \pi a constant: only t and \alpha are left
    assert answers['formulation'][0]['SymbolsUnknown'] == ['t', r'\alpha']


def test_a_symbol_is_not_found_inside_another():
    '''C, C_P and C_V are three symbols: the index belongs to the symbol, so C is not found in C_P.'''
    assert occurrences('C', r'C_P - C_V = R') == []
    assert occurrences('C', r'\gamma = \frac{C_{P}}{C_\text{V}}') == []
    assert occurrences('C', r'C = C_P + C_V') == [0]
    assert occurrences('C_P', r'C_{PV} + C_P V') == [2]
    answers = {'formulation': {
        0: page('heat', 'C = C_P + C_V', [('C', 'capacity'), ('C_P', 'isobaric'), ('C_V', 'isochoric')]),
        1: page('Mayer', 'C_P - C_V = R', [('R', 'gas constant')]),
    }}
    derive_symbols(answers)
    assert derived(answers['formulation'][1]) == {('C_P', 'isobaric', 'heat'), ('C_V', 'isochoric', 'heat')}
