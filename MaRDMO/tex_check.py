'''Check LaTeX formulas with the MaRDI Portal's TeX checker (texvc) before export.

The portal rejects ``math`` values its checker cannot parse, so formulas,
defining formulas and formula element symbols are checked in the preview and
the documentation checker.  The checker only gives a valid/invalid verdict
(``"syntax error"``); the preview adds MathJax's explanation in the browser.

Provides:

- :func:`check_formulas`   — portal verdict for a set of formulas (parallel, cached)
- :func:`check_formula`    — the verdict on one formula as typed in the interview (#190)
- :func:`collect_formulas` — all formulas and symbols of a model answers dict
- :func:`annotate_formulas` — store the verdicts next to the formulas for the preview
- :func:`environment_hint` — explanation for a rejection caused by an unsupported environment
- :data:`UNAVAILABLE`      — verdict when the checker could not be reached (try again)
- :data:`FAILED`           — verdict when the checker failed on a formula (not verified)

The checker answers 200 (valid) or 400 (invalid, with its message).  Other
answers mean that no verdict was reached: when the portal is not reachable
(no connection, timeout, 429, 502, 503, 504) the preview asks to try again;
when the checker itself fails on a formula (e.g. HTTP 500 for valid TeX the
portal saves and renders, #165) trying again does not help, so the formula
passes as "not verified by the MaRDI Portal".
'''
import hashlib
import logging
import re
from multiprocessing.pool import ThreadPool

import requests
from django.core.cache import cache
from django.utils.translation import gettext as _, ngettext

from .constants import TEX_CHECK_URL
from .writes import commit_writes
from .sources.http import SPARQL_RETRY_STATUS, request_with_retry
from .validators import normalize_formula

logger = logging.getLogger(__name__)

UNAVAILABLE = 'unavailable'
'''Verdict for formulas the checker could not answer: the portal is not reachable (try again).'''

FAILED = 'failed'
'''Verdict for formulas the checker failed on (no verdict): they pass as not verified.'''

NOT_VERIFIED = (UNAVAILABLE, FAILED)
'''Verdicts that are no verdict on the formula.'''

TEX_CHECK_TIMEOUT = 5
_CACHE_PREFIX = 'mardmo_tex_'
_CACHE_TIMEOUT = 7 * 24 * 60 * 60
# A failure of the checker is kept for a day: it does not go away by asking again
_FAILED_TIMEOUT = 24 * 60 * 60
_VALID = 'valid'
_MAX_THREADS = 8

# Answer sections whose entries carry defining formulas and formula elements
_FORMULA_SECTIONS = ('formulation', 'quantity')

# Environments accepted by the portal's checker (tested against production,
# 2026-10-27).  Starred variants (align*) and e.g. equation, gather, split or
# multline are rejected with a bare "syntax error", which environment_hint explains.
SUPPORTED_ENVIRONMENTS = (
    'aligned', 'alignedat', 'align', 'cases', 'array',
    'matrix', 'pmatrix', 'bmatrix', 'Bmatrix', 'vmatrix', 'Vmatrix', 'smallmatrix',
)
_ENVIRONMENT_RE = re.compile(r'\\begin\s*\{([^}]*)\}')


def environment_hint(tex):
    '''Explain a rejected formula that uses environments the portal does not support, or ``None``.

    The portal's checker only answers "syntax error"; KaTeX and MathJax render
    these environments, so without a hint the rejection is hard to understand.
    '''
    unsupported = sorted({
        name.strip() for name in _ENVIRONMENT_RE.findall(tex or '')
        if name.strip() not in SUPPORTED_ENVIRONMENTS
    })
    if not unsupported:
        return None
    return ngettext(
        '{environments} is not supported; supported environments are {supported}',
        '{environments} are not supported; supported environments are {supported}',
        len(unsupported),
    ).format(environments=', '.join(unsupported), supported=', '.join(SUPPORTED_ENVIRONMENTS))


# A text command in a subscript (``T_\mathrm{init}``, ``x_{\operatorname{max}}``): the
# portal's checker fails on it (HTTP 500), ``\text`` works (found 2026-11-17)
_SUBSCRIPT_COMMAND_RE = re.compile(r'_\s*\{?\s*\\(mathrm|operatorname)\b')


def failure_hint(tex):
    '''Explain why the portal's checker may have failed on *tex* (:data:`FAILED`), or ``None``.

    The checker fails (HTTP 500) on ``\\mathrm`` and ``\\operatorname`` in a
    subscript, although the portal saves and renders such a formula; with
    ``\\text`` the check works.
    '''
    commands = sorted(set(_SUBSCRIPT_COMMAND_RE.findall(tex or '')))
    if not commands:
        return None
    return _('the check fails on {commands} in a subscript; \\text{{…}} avoids that').format(
        commands=', '.join(f'\\{command}' for command in commands))


def _cache_key(tex):
    return _CACHE_PREFIX + hashlib.sha1(tex.encode('utf-8')).hexdigest()


def _checked_key(tex):
    '''Where the checker's form of a valid *tex* is kept (its ``checked``, #190).'''
    return _CACHE_PREFIX + 'checked_' + hashlib.sha1(tex.encode('utf-8')).hexdigest()


def _failed(tex, response):
    logger.warning("TeX check failed on %r: HTTP %s: %s", tex, response.status_code, response.text[:200])
    cache.set(_cache_key(tex), FAILED, _FAILED_TIMEOUT)
    return FAILED


def _check_one(tex):
    '''Return ``None`` (valid), the checker's message (invalid), :data:`UNAVAILABLE` or :data:`FAILED`.'''
    cached = cache.get(_cache_key(tex))
    if cached is not None:
        return None if cached == _VALID else cached
    try:
        response = request_with_retry(
            'post',
            TEX_CHECK_URL,
            data={'q': tex},
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            timeout=TEX_CHECK_TIMEOUT,
        )
    except requests.exceptions.RequestException as err:
        logger.warning("TeX check failed: %s", err)
        return UNAVAILABLE
    if response.status_code == 200:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if body.get('success') is not True:
            return _failed(tex, response)
        cache.set(_cache_key(tex), _VALID, _CACHE_TIMEOUT)
        # The checker's form, rendered where MathJax cannot render the formula as typed (#190)
        if isinstance(body.get('checked'), str):
            cache.set(_checked_key(tex), body['checked'], _CACHE_TIMEOUT)
        return None
    if response.status_code == 400:
        try:
            body = response.json()
        except ValueError:
            body = {}
        # Portal: {"message": ...}; Wikimedia/RESTBase: {"detail": {"details": ...}}
        detail = body.get('detail')
        message = (
            body.get('message')
            or (detail.get('details') if isinstance(detail, dict) else detail)
            or 'syntax error'
        )
        message = str(message)
        cache.set(_cache_key(tex), message, _CACHE_TIMEOUT)
        return message
    if response.status_code in SPARQL_RETRY_STATUS:
        logger.warning("TeX check returned HTTP %s: %s", response.status_code, response.text[:200])
        return UNAVAILABLE
    return _failed(tex, response)


def check_formulas(formulas):
    '''Check *formulas* with the portal's TeX checker.

    Requests run in parallel; verdicts are cached for a week, so repeated
    previews and checks do not resend unchanged formulas.  A request that
    times out or gets a 429/502/503/504 is retried once (see
    :func:`~MaRDMO.sources.http.request_with_retry`); failed requests are not cached.

    Args:
        formulas: Iterable of TeX strings (empty ones are skipped).

    Returns:
        Dict ``{tex: verdict}`` with ``None`` for valid formulas, the checker's
        message (e.g. ``"syntax error"``) for invalid ones, :data:`UNAVAILABLE`
        when the checker could not be reached, and :data:`FAILED` when it
        failed on the formula.
    '''
    # checked as exported: on one line, see normalize_formula
    unique = sorted({normalize_formula(tex) for tex in formulas if isinstance(tex, str)} - {''})
    if not unique:
        return {}
    commit_writes()
    with ThreadPool(processes=min(len(unique), _MAX_THREADS)) as pool:
        verdicts = pool.map(_check_one, unique)
    return dict(zip(unique, verdicts))


VALID, INVALID, UNVERIFIED = 'valid', 'invalid', 'unverified'
'''States of a formula checked while it is typed (:func:`check_formula`).'''


def check_formula(tex):
    '''The portal's verdict on one formula as typed in the interview (#190).

    Checked as exported, on one line, with :func:`check_formulas` (so with its
    cache: a formula checked while it is typed is not asked again by the
    preview, the checks or the export).

    Returns:
        ``{'state': …, 'message': …, 'checked': …}``: :data:`VALID` with the
        checker's form of the formula (``checked``, if the checker gave one);
        :data:`INVALID` with its message, and the explanation of an
        unsupported environment if there is one; :data:`UNVERIFIED` if the
        checker could not be reached or failed on the formula (no verdict,
        nothing for the user).
    '''
    one_line = normalize_formula(tex) if isinstance(tex, str) else ''
    if not one_line:
        return {'state': VALID, 'message': '', 'checked': ''}
    result = check_formulas([one_line]).get(one_line)
    if result is None:
        return {'state': VALID, 'message': '', 'checked': cache.get(_checked_key(one_line)) or ''}
    if result in NOT_VERIFIED:
        return {'state': UNVERIFIED, 'message': '', 'checked': ''}
    hint = environment_hint(one_line)
    return {'state': INVALID, 'message': f'{result} ({hint})' if hint else result, 'checked': ''}


def _formula_entries(answers):
    '''Yield ``(entry, formulas, elements)`` for every formula-carrying answer entry.'''
    for section in _FORMULA_SECTIONS:
        for entry in answers.get(section, {}).values():
            if isinstance(entry, dict):
                yield entry, entry.get('Formula') or {}, entry.get('element') or {}


def collect_formulas(answers):
    '''Return all formulas and element symbols of a model answers dict.'''
    formulas = set()
    for _entry, formula_dict, elements in _formula_entries(answers):
        formulas.update(formula_dict.values())
        formulas.update(e.get('symbol') for e in elements.values() if isinstance(e, dict))
    return formulas


def verdict(verdicts, tex):
    '''Look up the verdict for *tex* in a :func:`check_formulas` result.'''
    if not isinstance(tex, str) or not normalize_formula(tex):
        return None
    return verdicts.get(normalize_formula(tex))


def annotate_formulas(answers):
    '''Check all formulas of *answers* and store the verdicts for the preview.

    Adds ``FormulaCheck`` (``{index: verdict}``) to every entry with formulas
    and ``symbol_check`` to every formula element.
    '''
    verdicts = check_formulas(collect_formulas(answers))
    for entry, formula_dict, elements in _formula_entries(answers):
        entry['FormulaCheck'] = {idx: verdict(verdicts, tex) for idx, tex in formula_dict.items()}
        for element in elements.values():
            if isinstance(element, dict):
                element['symbol_check'] = verdict(verdicts, element.get('symbol'))
    return answers
