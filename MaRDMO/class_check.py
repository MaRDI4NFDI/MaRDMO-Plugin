'''Which Wikidata items fit a dropdown, by their classes (#170).

A dropdown offers Wikidata items of certain kinds only: those that are an
instance or a subclass of something at or below its *roots* (e.g. software
for the software dropdown), or, where no class fits (research problems),
those that are not an instance of a class of a *noise* list (persons, taxa,
articles, …).  :func:`wikidata_matches` answers this for the hits of a
search with one SPARQL query, walking from each item's classes upwards.

QLever's Wikidata endpoint (updated live) answers such queries in a fraction
of a second; Wikidata's own endpoint is asked if QLever fails.  If both fail
the caller shows the hits unfiltered, as before.  Answers are cached per item
and set of classes, so items found again are not checked again.
'''

import hashlib
import json
import logging
import re
import time

from django.core.cache import cache

from . import queries
from .constants import WIKIDATA

logger = logging.getLogger(__name__)

# Class memberships rarely change; a checked item is not checked again for so long
CLASS_CHECK_TIMEOUT = 24 * 60 * 60
# QLever answers within a second; a longer wait leaves no time for Wikidata's endpoint
QLEVER_TIMEOUT = 3

# Only these go into a query; anything else (e.g. typed by a user) does not fit
QID = re.compile(r'Q[1-9][0-9]*')

PREFIXES = (
    'PREFIX wd: <http://www.wikidata.org/entity/>\n'
    'PREFIX wdt: <http://www.wikidata.org/prop/direct/>\n'
)


def _qid(item):
    '''*item* as a bare QID (``wikidata:Q42`` → ``Q42``).'''
    return item.removeprefix('wikidata:')


def _values(name, qids):
    return f'VALUES ?{name} {{ {" ".join(f"wd:{qid}" for qid in sorted(qids))} }}'


def query_roots(qids, roots, wikidata=False):
    '''The query for the *qids* that are an instance or subclass of something at or below *roots*.

    The path is walked upwards from each item's classes; walked downwards from
    a broad root (software has thousands of subclasses) it takes many seconds.
    QLever does that by itself, Wikidata's endpoint (*wikidata*) is told to.
    '''
    gearing = ' hint:Prior hint:gearing "forward" .' if wikidata else ''
    return (f'SELECT DISTINCT ?item WHERE {{\n'
            f'  {_values("item", qids)}\n'
            f'  {{ ?item wdt:P31 ?class . }} UNION {{ ?item wdt:P279 ?class . }}\n'
            f'  ?class wdt:P279* ?root .{gearing}\n'
            f'  {_values("root", roots)}\n'
            f'}}')


def query_noise(qids, noise, wikidata=False):
    '''The query for the *qids* that are an instance of a class of *noise* or of one of its subclasses.'''
    gearing = ' hint:Prior hint:gearing "forward" .' if wikidata else ''
    return (f'SELECT DISTINCT ?item WHERE {{\n'
            f'  {_values("item", qids)}\n'
            f'  ?item wdt:P31 ?class .\n'
            f'  ?class wdt:P279* ?noise .{gearing}\n'
            f'  {_values("noise", noise)}\n'
            f'}}')


def _found(qids, build, deadline):
    '''The *qids* the query of *build* returns: QLever first, then Wikidata's endpoint; ``None`` if both fail.'''
    rows = queries.query_sparql(PREFIXES + build(qids, wikidata=False), WIKIDATA['qlever'], strict=True,
                                waits=(), deadline=time.monotonic() + QLEVER_TIMEOUT)
    if rows is None:
        logger.warning('Class check: QLever failed; asking Wikidata.')
        rows = queries.query_sparql(build(qids, wikidata=True), WIKIDATA['sparql'], strict=True, waits=(),
                                    deadline=deadline)
    if rows is None:
        logger.warning('Class check: QLever and Wikidata failed; the hits are not filtered.')
        return None
    return {row['item']['value'].rsplit('/', 1)[-1] for row in rows}


def wikidata_matches(items, roots=None, noise=None, deadline=None):
    '''Which Wikidata *items* fit: ``{QID: bool}``, or ``None`` if the check failed.

    With *roots*, an item fits if it is an instance or a subclass of
    something at or below one of them.  With *noise* (where no class fits),
    an item fits if it is not an instance of a class of *noise* or of one
    of its subclasses.  *items* may be QIDs or ``wikidata:`` IDs; the answer
    is keyed by QID.  Anything that is not a QID does not fit and is not
    asked for.

    Args:
        items:    QIDs or ``wikidata:`` IDs, e.g. the hits of a label search.
        roots:    QIDs of the classes an item must be at or below.
        noise:    QIDs of the classes an item must not be an instance of.
        deadline: :func:`time.monotonic` value by which Wikidata's endpoint
                  must answer (default: a search's, :func:`~.queries.search_deadline`).

    Returns:
        ``{QID: True/False}`` for every item; ``None`` if QLever and
        Wikidata's endpoint both failed (nothing of it is cached).
    '''
    if (roots is None) == (noise is None):
        raise ValueError('wikidata_matches needs either roots or noise')
    if not all(QID.fullmatch(cls) for cls in (roots if roots is not None else noise)):
        raise ValueError('roots and noise must be QIDs')
    qids = list(dict.fromkeys(_qid(item) for item in items))
    if not qids:
        return {}
    classes = sorted(roots if roots is not None else noise)
    scope = hashlib.sha1(json.dumps(['roots' if roots is not None else 'noise', classes]).encode()).hexdigest()
    known = {qid: False for qid in qids if not QID.fullmatch(qid)}
    keys = {qid: f'mardmo_class_{scope}_{qid}' for qid in qids if qid not in known}
    cached = cache.get_many(list(keys.values()))
    known.update({qid: cached[key] for qid, key in keys.items() if key in cached})
    unknown = [qid for qid in qids if qid not in known]
    if unknown:
        if roots is not None:
            found = _found(unknown, lambda q, wikidata: query_roots(q, classes, wikidata), deadline
                           or queries.search_deadline())
        else:
            found = _found(unknown, lambda q, wikidata: query_noise(q, classes, wikidata), deadline
                           or queries.search_deadline())
        if found is None:
            return None
        # With roots the query returns the items that fit, with noise those that do not
        checked = {qid: (qid in found) == (roots is not None) for qid in unknown}
        cache.set_many({keys[qid]: fits for qid, fits in checked.items()}, CLASS_CHECK_TIMEOUT)
        known.update(checked)
    return {qid: known[qid] for qid in qids}
