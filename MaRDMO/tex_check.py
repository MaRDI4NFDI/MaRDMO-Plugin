'''Check LaTeX formulas with the MaRDI Portal's TeX checker (texvc) before export.

The portal rejects ``math`` values its checker cannot parse, so formulas,
defining formulas and formula element symbols are checked in the preview and
the documentation checker.  The checker only gives a valid/invalid verdict
(``"syntax error"``); the preview adds MathJax's explanation in the browser.

Provides:

- :func:`check_formulas`   — portal verdict for a set of formulas (parallel, cached)
- :func:`collect_formulas` — all formulas and symbols of a model answers dict
- :func:`annotate_formulas` — store the verdicts next to the formulas for the preview
- :data:`UNAVAILABLE`      — verdict when the checker could not be reached
'''
import hashlib
import logging
from multiprocessing.pool import ThreadPool

import requests
from django.core.cache import cache

from .constants import TEX_CHECK_URL

logger = logging.getLogger(__name__)

UNAVAILABLE = 'unavailable'
'''Verdict for formulas the checker could not answer (timeout, server error).'''

TEX_CHECK_TIMEOUT = 5
_CACHE_PREFIX = 'mardmo_tex_'
_CACHE_TIMEOUT = 7 * 24 * 60 * 60
_VALID = 'valid'
_MAX_THREADS = 8

# Answer sections whose entries carry defining formulas and formula elements
_FORMULA_SECTIONS = ('formulation', 'quantity')


def _cache_key(tex):
    return _CACHE_PREFIX + hashlib.sha1(tex.encode('utf-8')).hexdigest()


def _check_one(tex):
    '''Return ``None`` (valid), the checker's message (invalid), or :data:`UNAVAILABLE`.'''
    cached = cache.get(_cache_key(tex))
    if cached is not None:
        return None if cached == _VALID else cached
    try:
        response = requests.post(
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
            valid = response.json().get('success') is True
        except ValueError:
            valid = False
        if not valid:
            logger.warning("TeX check returned an unexpected answer: %s", response.text[:200])
            return UNAVAILABLE
        cache.set(_cache_key(tex), _VALID, _CACHE_TIMEOUT)
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
    logger.warning("TeX check returned HTTP %s: %s", response.status_code, response.text[:200])
    return UNAVAILABLE


def check_formulas(formulas):
    '''Check *formulas* with the portal's TeX checker.

    Requests run in parallel; verdicts are cached for a week, so repeated
    previews and checks do not resend unchanged formulas.  Failed requests are
    not cached.

    Args:
        formulas: Iterable of TeX strings (empty ones are skipped).

    Returns:
        Dict ``{tex: verdict}`` with ``None`` for valid formulas, the checker's
        message (e.g. ``"syntax error"``) for invalid ones, and
        :data:`UNAVAILABLE` when the checker could not be reached.
    '''
    unique = sorted({tex.strip() for tex in formulas if isinstance(tex, str) and tex.strip()})
    if not unique:
        return {}
    with ThreadPool(processes=min(len(unique), _MAX_THREADS)) as pool:
        verdicts = pool.map(_check_one, unique)
    return dict(zip(unique, verdicts))


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
    if not isinstance(tex, str) or not tex.strip():
        return None
    return verdicts.get(tex.strip())


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
