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
        'b', 's', 'i', r'\mathrm{if}', r'\begin{cases}', 'a', r'\end{cases}']
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


def page(tab, tex=None, rows=(), identifier=None):
    entry = {'Tab': tab, 'ID': identifier or f'user:{tab}', 'element': {index: {'symbol': symbol, 'quantity': {'ID': quantity, 'Name': quantity}}
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


# --- Cases of the MaRDI Portal's models (#179) -------------------------------------------------

def test_upright_is_another_symbol_than_italic():
    '''``\\mathrm{i}`` is the imaginary unit (portal Q6481153), ``i`` an index or a variable.'''
    assert canonical(r'\mathrm{i}') != canonical('i') and canonical(r'\mathrm{i}') == canonical(r'\text{i}')
    answers = {'quantity': {0: page('imaginary unit', r'\mathrm{i} \equiv \sqrt{-1}', [(r'\mathrm{i}', 'imaginary unit')])},
               'formulation': {0: page('wave', r'\psi = e^{\mathrm{i} \omega t} + x_i + i', [(r'\psi', 'wave function')])}}
    derive_symbols(answers)
    assert derived(answers['formulation'][0]) == {(r'\mathrm{i}', 'imaginary unit', 'imaginary unit')}


def test_an_operator_written_as_a_row_defines_nothing():
    '''The portal's "imaginary unit" has the row ``^2`` for "square": it is not found in every square.'''
    answers = {'quantity': {0: page('imaginary unit', r'\mathrm{i} \equiv \sqrt{-1}', [('^2', 'square')])},
               'formulation': {0: page('energy', r'E = m c^2', [('E', 'energy')])}}
    derive_symbols(answers)
    assert derived(answers['formulation'][0]) == set()


def test_the_variable_of_a_derivative_counts_inside_a_longer_symbol():
    '''Portal Theorell-Chance models: the derivative is a row of its own, its ``t`` is used all the same.'''
    answers = {'formulation': {
        0: page('ODE system', r'\frac{dc_{E}}{dt} = k_{1} c_{E}', [(r'\frac{dc_{E}}{dt}', 'rate'), ('c_{E}', 'enzyme'),
                                                                  ('k_{1}', 'rate constant'), ('t', 'time')]),
        1: page('enzyme ODE', r'\frac{dc_{E}}{dt} = - k_{1} c_{E}', [(r'\frac{dc_{E}}{dt}', 'rate')]),
        2: page('heat equation', r'\partial_t u = \Delta u', [('u', 'temperature')]),
    }}
    derive_symbols(answers)
    assert ('t', 'time', 'ODE system') in derived(answers['formulation'][1])
    assert derived(answers['formulation'][2]) == {('t', 'time', 'ODE system')}


def test_a_symbol_inside_a_longer_symbol_is_used():
    '''Portal models: rows ``s_m(t)`` and ``\\frac{D_A}{h^2}`` use ``t``, ``D_A`` and ``h`` all the same.'''
    answers = {'formulation': {
        0: page('ODE system', r'\frac{ds_m(t)}{dt} = -D_A s_m(t)', [('s_m(t)', 'susceptible'), ('t', 'time'),
                                                                   ('D_A', 'diffusion'), ('h', 'grid width')]),
        1: page('conservation', r'i_m(t) = P_m - s_m(t)', [('i_m(t)', 'infected'), ('P_m', 'population')]),
        2: page('jump rate', r'd_A \equiv \frac{D_A}{h^2}', [('d_A', 'jump rate'), (r'\frac{D_A}{h^2}', 'jump rate')]),
    }}
    derive_symbols(answers)
    assert derived(answers['formulation'][1]) == {('s_m(t)', 'susceptible', 'ODE system'), ('t', 'time', 'ODE system')}
    assert derived(answers['formulation'][2]) == {('D_A', 'diffusion', 'ODE system'), ('h', 'grid width', 'ODE system')}


@pytest.mark.parametrize('tex, row', [(r'\Delta t = 1', r'\Delta t'), (r'\tilde{A} = A^*', r'\tilde{A}'),
                                      (r'\overline{\mathbf{A}} = 0', r'\overline{\mathbf{A}}'),
                                      ('D_1(0) = A_G D', 'D_1(0)'), (r'y \leq score_{max}', 'score_{max}'),
                                      (r'\frac{Z_l}{RZ}', 'RZ')])
def test_a_symbol_the_longer_symbol_is_made_of_is_not_used(tex, row):
    '''chowdhury_2020: ``D_1(0)``, the value at 0, is a symbol of its own; its formulas do not use ``D_1``.

    The portal's ``score_{max}`` and ``RZ`` are names in letters: no ``o``, no ``Z`` in them.
    '''
    inner = {r'\Delta t': 't', r'\tilde{A}': 'A', r'\overline{\mathbf{A}}': r'\mathbf{A}', 'D_1(0)': 'D_1',
             'score_{max}': 'o', 'RZ': 'Z'}[row]
    answers = {'formulation': {0: page('a', f'{inner} = 0', [(inner, 'plain')]),
                               1: page('b', tex, [(row, 'modified')])}}
    derive_symbols(answers)
    assert derived(answers['formulation'][1]) == set()


def test_an_indexed_variant_is_another_symbol():
    '''``t_1`` is not ``t`` (portal Gramians): such a formula needs the row itself (the help says so).'''
    answers = {'formulation': {0: page('a', 't = 0', [('t', 'time')]),
                               1: page('Gramian', r'P_{1}(t_{1}) \equiv e^{A t_{1}} B', [('A', 'matrix')])}}
    derive_symbols(answers)
    assert all(symbol != 't' for symbol, _, _ in derived(answers['formulation'][1]))


def test_a_portal_item_keeps_its_table():
    '''Only the user's own items get rows: a portal formula's table stays as the portal has it.'''
    answers = {'formulation': {0: page('own', 'T = t', [('T', 'temperature'), ('t', 'time')]),
                               1: page('portal', 'T(t) = T_0 e^{-t}', identifier='mardi:Q1')}}
    derive_symbols(answers)
    assert derived(answers['formulation'][1]) == set() and 'SymbolsUnknown' not in answers['formulation'][1]


def test_a_portal_item_defines_symbols_for_the_users_items():
    '''Rows go one way: a portal formula's row comes to the user's formulas, and counts for ambiguity.'''
    answers = {'formulation': {0: page('portal', 'x = v t', [('t', 'time')], identifier='mardi:Q1'),
                               1: page('own', 'y = t^2', [('y', 'height')])}}
    derive_symbols(answers)
    assert derived(answers['formulation'][1]) == {('t', 'time', 'portal')}
    answers['formulation'][2] = page('other', 's = t', [('t', 'duration')])
    answers['formulation'][3] = page('third', 'z = t', [('z', 'height')])
    derive_symbols(answers)
    assert answers['formulation'][3]['SymbolsAmbiguous'] == {'t': ['other', 'portal']}
    assert derived(answers['formulation'][0]) == set() and 'SymbolsAmbiguous' not in answers['formulation'][0]
