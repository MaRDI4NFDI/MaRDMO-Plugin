'''The symbols of the formulas: defined once, used in every formula (#179).

A symbol that stands for the same quantity in all formulas of a
documentation needs one row in one symbol table (of a formula or a quantity
definition); every other formula of the user's own items that uses it gets the
row derived (a MaRDI Portal item's table stays as the portal has it, but
defines symbols for the others).  A
symbol that stands for different quantities needs a row in every formula
that uses it.  Own rows always take precedence; nothing is written to the
project: the rows are derived each time the answers are read
(:func:`derive_symbols`, from :meth:`MaRDMO.model.worker.PrepareModel.preview`),
so the checks, the preview and the payload see the same tables.

"Uses" means: the symbol occurs in the formula's TeX as a whole symbol.  TeX
is read as tokens — a command, a word in ``\\text{}``/``\\mathrm{}``, a letter
(every letter of a formula is a symbol of its own: ``bx`` is *b* times *x*),
a digit, a character — and an index (``_0``, ``_{\\text{init}}``) or a star
belongs to the symbol before it.  The longest symbol wins (``\\Delta t`` before
``t``, ``D_1(0)`` before ``D_1``), and ``d`` at the start of a fraction's part
or after a thin space (``\\frac{dT}{dt}``, ``\\, dx``) is the differential.  A
symbol inside a longer one is used as well (the ``t`` of a row ``s(t)`` or
``\\frac{dc}{dt}``, the ``D`` of ``\\frac{D}{h^2}``, and of ``\\partial_t``), but not
at its start, under an accent or an operator, or in a name written in letters
(``D_1`` of ``D_1(0)``, ``\\Delta t``, ``\\tilde{A}``, the ``o`` of ``score_{max}``).  Upright is another symbol than
italic (``\\mathrm{i}``, the imaginary unit, and ``i``); a row that does not
start with a symbol (``^2`` for "square") defines nothing for other formulas.
'''
import re

from django.utils.translation import gettext as _

from ..core.ids import is_portal_item

# The sections whose pages have a formula and a symbol table
SECTIONS = ('formulation', 'quantity')

_TOKEN = re.compile(r'''
    \\(?:begin|end)\s*\{[^{}]*\}                                         # an environment
  | \{\s*\\rm\s+[^{}]*\}                                                 # {\rm m}: a word
  | \\(?:text|textrm|textit|mathrm|mathit|operatorname|rm)\s*\{[^{}]*\}   # a word
  | \\[A-Za-z]+                                                          # a command
  | \\.                                                                  # \, \; \{ ...
  | [A-Za-z0-9]
  | \S
''', re.VERBOSE)
# What only sets a font: left out of an index or a label (A_\text{m} is A_m)
# A superscript that is a label, not a power: only a word in a font (C^\text{f}, C^{\rm f}),
# not an exponent that contains one (e^{\mathrm{i} \omega t})
_LABEL = re.compile(r'\{?\s*\\(?:text|textrm|textit|mathrm|mathit|rm)\s*(?:\{[^{}]*\}|\w+)\s*\}?')
_WRAPPERS = re.compile(r'\\(?:text|textrm|textit|mathrm|mathit|rm)\b\s*')

GREEK = {
    'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'varepsilon', 'zeta', 'eta', 'theta', 'vartheta', 'iota',
    'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'varpi', 'rho', 'varrho', 'sigma', 'varsigma', 'tau', 'upsilon',
    'phi', 'varphi', 'chi', 'psi', 'omega', 'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma',
    'Upsilon', 'Phi', 'Psi', 'Omega', 'ell', 'hbar',
}
# Commands that write a symbol in another font: \mathcal{L} is a symbol of its own
_FONTS = {'mathcal', 'mathbb', 'mathbf', 'mathfrak', 'mathsf', 'boldsymbol', 'bm', 'mathscr', 'textbf'}
# What may stand before a differential: d at the start, after {, a space, an operator, an integral
_BEFORE_DIFFERENTIAL = {'{', '(', '=', '+', '-', '&', r'\,', r'\;', r'\:', r'\!', r'\quad', r'\qquad',
                        r'\int', r'\iint', r'\iiint', r'\oint'}
# Not quantities, however written: the circle constant; operators before a symbol (\Delta x, \nabla u)
_CONSTANTS = {r'\pi'}
_OPERATORS = {r'\Delta', r'\nabla'}
# What makes another symbol of the one after it, inside a longer symbol: \Delta t is not t, \tilde{A} not A
_MODIFIERS = _OPERATORS | {'\\' + accent for accent in (
    'hat', 'widehat', 'tilde', 'widetilde', 'bar', 'overline', 'underline', 'vec', 'overrightarrow',
    'dot', 'ddot', 'dddot', 'check', 'breve', 'acute', 'grave', 'mathring')}


class Token(str):
    '''A token of a formula: its canonical text; ``upright`` for a word (``\\mathrm{d}``).'''
    upright = False


def _group(raw, start):
    '''The balanced ``{...}`` of *raw* at *start* (or the single token there) and the position after it.'''
    if raw[start] != '{':
        match = _TOKEN.match(raw, start)
        return (match.group(), match.end()) if match else ('', start + 1)
    depth = 0
    for position in range(start, len(raw)):
        depth += {'{': 1, '}': -1}.get(raw[position], 0)
        if depth == 0:
            return raw[start:position + 1], position + 1
    return raw[start:], len(raw)


def _label(group):
    '''An index or a label without font, braces and spaces: ``{\\text{eff}}`` and ``{\\rm eff}`` are ``eff``.'''
    return re.sub(r'[\s{}]', '', _WRAPPERS.sub('', group))


def _word(text):
    '''The text of a word token (``\\mathrm{d}`` -> ``d``, ``{\\rm m}`` -> ``m``).'''
    return _label(re.sub(r'^\{?\s*\\(?:text|textrm|textit|mathrm|mathit|operatorname|rm)', '', text))


def tokens(tex):
    '''The tokens of *tex*: a symbol with its index, label and primes as one canonical token.

    ``T_{0}`` and ``T_0``, ``A_\\text{m}`` and ``A_m``, ``V^\\text{f}_\\text{m}``
    and ``V_{m}^{f}`` give the same token; a power (``x^2``) is not part of
    the symbol, a star or a label is (``x^*``, ``C^\\text{f}``).
    '''
    raw, out, position = tex or '', [], 0
    while True:
        match = _TOKEN.search(raw, position)
        if not match:
            return out
        text, position = match.group(), match.end()
        upright = False
        if re.match(r'\{?\s*\\(?:text|textrm|textit|mathrm|mathit|operatorname|rm)\b', text):
            # Upright is another symbol than italic (\mathrm{i} the imaginary unit, i an index);
            # in an index or a label the font does not matter (_label)
            text, upright = r'\mathrm{' + _word(text) + '}', True
        elif text.startswith('\\') and text[1:] in _FONTS:
            spaced = position + re.match(r'\s*', raw[position:]).end()
            if spaced < len(raw):
                group, position = _group(raw, spaced)
                text = (r'\mathbf' if text == r'\textbf' else text) + '{' + _label(group) + '}'
        sub, sup, primes = '', '', ''
        while True:
            spaced = position + re.match(r'\s*', raw[position:]).end()
            if spaced >= len(raw) or raw[spaced] not in "_^'":
                break
            mark = raw[spaced]
            if mark == "'":
                primes, position = primes + "'", spaced + 1
                continue
            group, end = _group(raw, spaced + 1 + re.match(r'\s*', raw[spaced + 1:]).end()) \
                if spaced + 1 < len(raw) else ('', spaced + 1)
            label = _label(group)
            if mark == '^' and not (label in ('*', r'\ast', r'\star', r'\prime') or _LABEL.fullmatch(group.strip())):
                break                                     # a power: not part of the symbol
            if mark == '_':
                sub = label
            else:
                sup = r"'" if label == r'\prime' else label
            position = end
        token = Token(text + (f'_{{{sub}}}' if sub else '') + (f'^{{{sup}}}' if sup else '') + primes)
        token.upright = upright
        out.append(token)


def _base(token):
    return re.split(r"[_^']", token, maxsplit=1)[0]


def is_symbol(token):
    '''Whether *token* can be a quantity's symbol: a letter or a Greek letter (with index), a font command.'''
    base = _base(token)
    return bool(re.fullmatch(r'[A-Za-z]|\\mathrm\{[A-Za-z]\}', base)) or base[1:] in GREEK or (
        base.startswith('\\') and base[1:].split('{', 1)[0] in _FONTS)


def _differential(found, index):
    '''Whether the token at *index* is the differential (``\\frac{dT}{dt}``, ``d a = c\\, dt``, ``\\mathrm{d}x``).'''
    token = found[index]
    if token not in ('d', r'\mathrm{d}') or index + 1 >= len(found) or not is_symbol(found[index + 1]):
        return False
    return token.upright or index == 0 or found[index - 1] in _BEFORE_DIFFERENTIAL


def _variables(found):
    '''The positions and symbols of the variables of the partial derivatives in *found*.

    ``t`` of ``\\partial_t`` is used by the formula, though it is the index of a token.
    '''
    for index, token in enumerate(found):
        if _base(token) == r'\partial' and '_{' in token:
            yield index, canonical(token.split('_{', 1)[1].split('}', 1)[0])


def _made_of(found, index, length):
    '''Whether the symbol at *index* (*length* tokens) is a part another symbol is made of, not one it uses.

    An accent or an operator stands on it (``\\Delta t``, ``\\tilde{A}``), or it
    is a letter of a name written in letters (the ``o`` of ``score_{max}``, the
    ``Z`` of ``RZ``); the differential before it is no letter (``\\frac{dc}{dt}``).
    '''
    def letter(position):
        return 0 <= position < len(found) and bool(re.fullmatch(r'[A-Za-z]', _base(found[position])))
    before = index - 1
    while before >= 0 and found[before] == '{':
        before -= 1
    return (before >= 0 and found[before] in _MODIFIERS) or (letter(index - 1) and not _differential(found, index - 1)) \
        or letter(index + length)


def occurrences(symbol, tex):
    '''The positions in the tokens of *tex* where *symbol* is written as a whole symbol.'''
    wanted, found = tokens(symbol), tokens(tex)
    if not wanted:
        return []
    return [index for index in range(len(found) - len(wanted) + 1)
            if found[index:index + len(wanted)] == wanted
            and not (len(wanted) == 1 and _differential(found, index))]


def canonical(symbol):
    '''A symbol as its tokens: ``T_{0}`` and ``T_0``, ``A_\\text{m}`` and ``A_m`` are the same symbol.'''
    return ' '.join(tokens(symbol))


def formulas_of(page):
    '''The TeX of the formulas of *page* (one, or by collection index).'''
    formula = page.get('Formula')
    if isinstance(formula, dict):
        return [text for _, text in sorted(formula.items()) if text]
    return [formula] if formula else []


def definitions(answers):
    '''``{canonical symbol: {quantity ID: (quantity, tab)}}`` of the rows of every symbol table.

    A row counts with its quantity (its ID); the tab is the first page that has it.
    '''
    found = {}
    for section in SECTIONS:
        for page in (answers.get(section) or {}).values():
            if not isinstance(page, dict):
                continue
            for element in (page.get('element') or {}).values():
                quantity = element.get('quantity') if isinstance(element, dict) else None
                if not element.get('symbol') or not isinstance(quantity, dict) or not quantity.get('ID'):
                    continue
                key = canonical(element['symbol'])
                if not _defines(key):
                    continue
                found.setdefault(key, {}).setdefault(quantity['ID'], (quantity, page.get('Tab') or page.get('Name', '')))
    return found


def _defines(key):
    '''Whether a row with the canonical symbol *key* defines it for other formulas.

    It starts with a symbol (``T``, ``\\mathbf{x}``) or a command that makes one
    (``\\frac``, ``\\hat``); an operator written as a row (``^2`` for "square")
    does not: it would stand wherever something is squared.
    '''
    first = key.split(' ', 1)[0]
    return is_symbol(first) or bool(re.fullmatch(r'\\[A-Za-z]+', _base(first)))


def derive_symbols(answers):
    '''Complete the symbol tables of *answers* from the rows of the documentation (mutated in place).

    Every page with a formula gets a derived row (``derived``: the tab it comes
    from) for each symbol of the documentation that its TeX uses and its own
    table lacks, if the symbol stands for one quantity only.  A symbol it uses
    that stands for several quantities, without an own row, goes into
    ``SymbolsAmbiguous`` (``{symbol: [tabs]}``); a letter of its TeX that no
    table defines into ``SymbolsUnknown``.

    Returns:
        *answers*.
    '''
    defined = definitions(answers)
    # Longest first: \Delta t before t, D_1(0) before D_1
    by_length = sorted(defined, key=lambda key: -len(key.split(' ')))
    for section in SECTIONS:
        for page in (answers.get(section) or {}).values():
            if not isinstance(page, dict):
                continue
            texts = formulas_of(page)
            if not texts or is_portal_item(page.get('ID')):
                continue                                  # a portal item's table stays as the portal has it
            elements = page.setdefault('element', {})
            own = {canonical(element['symbol']) for element in elements.values()
                   if isinstance(element, dict) and element.get('symbol')}
            ambiguous, used = {}, {}               # used: key -> (formula, position) of its first use
            for tex in texts:
                found, taken, longer = tokens(tex), set(), []
                for key in by_length:
                    length = len(key.split(' '))
                    for index in occurrences(key, tex):
                        span = set(range(index, index + length))
                        if span & taken:
                            # inside a longer symbol: used (the t of s(t)), not where the longer symbol is
                            # made of it: at its start (D_1 of D_1(0)), under an accent (\Delta t), in a name (RZ)
                            if any(span < outer and index != min(outer) for outer in longer) \
                                    and not _made_of(found, index, length) and key not in own:
                                used.setdefault(key, (texts.index(tex), index))
                            continue
                        taken |= span
                        if length > 1:
                            longer.append(span)
                        if key not in own:
                            used.setdefault(key, (texts.index(tex), index))
                for index, variable in _variables(found):
                    if variable in defined and variable not in own:
                        used.setdefault(variable, (texts.index(tex), index))
                for index, token in enumerate(found):
                    nxt = found[index + 1] if index + 1 < len(found) else ''
                    exponential = token in ('e', r'\mathrm{e}') and nxt == '^'
                    operator = token in _OPERATORS and is_symbol(nxt)
                    if index not in taken and is_symbol(token) and not _differential(found, index) \
                            and not (exponential or operator or token in _CONSTANTS) and str(token) not in own:
                        page.setdefault('SymbolsUnknown', [])
                        if token not in page['SymbolsUnknown']:
                            page['SymbolsUnknown'].append(str(token))
            number = max([key for key in elements if isinstance(key, int)], default=-1) + 1
            for key in sorted(used, key=used.get):
                quantities = defined[key]
                if len(quantities) > 1:
                    ambiguous[key] = sorted({tab for _, tab in quantities.values()})
                    continue
                quantity, tab = next(iter(quantities.values()))
                elements[number] = {'symbol': _symbol_text(key, answers), 'quantity': dict(quantity), 'derived': tab}
                number += 1
            if ambiguous:
                page['SymbolsAmbiguous'] = {_symbol_text(key, answers): tabs for key, tabs in sorted(ambiguous.items())}
    return answers


def _symbol_text(key, answers):
    '''The symbol *key* as the first row of the documentation writes it.'''
    for section in SECTIONS:
        for page in (answers.get(section) or {}).values():
            for element in (page.get('element') or {}).values() if isinstance(page, dict) else ():
                if isinstance(element, dict) and element.get('symbol') and canonical(element['symbol']) == key \
                        and not element.get('derived'):
                    return element['symbol']
    return key


def ambiguous_message(symbol, tabs):
    '''The problem of a symbol that stands for several quantities and has no row in this table.'''
    return _('Symbol "{symbol}" stands for different quantities in this documentation (cf. pages {tabs}): '
             'enter it in this table too').format(symbol=symbol, tabs=', '.join(f'"{tab}"' for tab in tabs))


def unknown_message(symbols):
    '''The hint for letters of a formula that no symbol table defines.'''
    return _('No symbol table defines {symbols}: if they stand for quantities, enter them in this table').format(
        symbols=', '.join(f'"{symbol}"' for symbol in symbols))
