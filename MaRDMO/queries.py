'''Functions that query external data sources (Wikibase API, SPARQL endpoints, Crossref, etc.).

Provides helpers for:

* ``query_api`` – Wikibase ``wbsearchentities`` lookups
* ``find_portal_items`` – duplicates, Wikidata twins and markers on the MaRDI Portal (#141)
* ``query_sources`` / ``query_sources_with_user_additions`` – combined
  MaRDI + Wikidata search with optional user-defined entries
* ``query_api_per_class`` – class-filtered full-text search on the MaRDI portal
* ``query_api_per_profile`` – search of the MaRDI portal by MaRDI profile (faceted search)
* ``option_help`` – the layout of a dropdown option (badge, label, description)

The requests themselves (session, retries, time limits, SPARQL):
:mod:`MaRDMO.sources.http`.
'''
import hashlib
import html
import json
import logging
import re
from dataclasses import dataclass, field
from itertools import zip_longest
from multiprocessing.pool import ThreadPool

import requests
from django.core.cache import cache
from rdmo.domain.models import Attribute

from .class_check import wikidata_matches
from .constants import BASE_URI
from .getters import get_mathmoddb, get_properties, get_url
from .sources.http import (
    SEARCH_RETRY_WAIT,
    SEARCH_TIMEOUT,
    query_sparql,
    request_with_retry,
    search_deadline,
)
from .values import extract_parts
from .ids import (
    DOI_PREFIX, NEW_DOI, NEW_ITEM, NOT_FOUND, is_item_id, is_user_id, item_text, publication_doi,
)

logger = logging.getLogger(__name__)

# Search results of the MaRDI Portal and Wikidata are reused for this long
SEARCH_CACHE_TIMEOUT = 5 * 60
# Hits of a Wikidata label search: 10 shown unfiltered; 50 asked for where
# they are filtered by their classes, which leaves out most of them (#170)
WIKIDATA_HITS = 10
WIKIDATA_FILTERED_HITS = 50


# Results of find_portal_items are reused for this long: the preview looks
# them up, the export takes them from there (#141)
PORTAL_LOOKUP_TIMEOUT = 15 * 60
# Pairs and IDs per SPARQL query of find_portal_items
PORTAL_LOOKUP_CHUNK = 50


@dataclass
class PortalItems:
    '''What :func:`find_portal_items` found on the MaRDI Portal.

    ``by_label``: ``{(label, description): QID or None}``; ``by_wikidata``:
    ``{Wikidata QID: QID or None}``; ``markers``: ``{QID: {'class': set,
    'community': set, 'profile': set}}``.  A lookup that could not be
    completed leaves its keys out and sets its flag (``label_failed`` ...).
    '''
    by_label: dict = field(default_factory=dict)
    by_wikidata: dict = field(default_factory=dict)
    markers: dict = field(default_factory=dict)
    label_failed: bool = False
    wikidata_failed: bool = False
    markers_failed: bool = False
    # Publications by their DOI (#158, duplicates.look_up): {DOI in upper case: (QID, label, description)}
    by_doi: dict = field(default_factory=dict)
    doi_failed: bool = False


def _sparql_literal(text):
    '''*text* as an English SPARQL string literal.'''
    return json.dumps(text, ensure_ascii=False) + '@en'


def _cached_lookup(kind, keys, query, waits, deadline):
    '''Look up *keys* (see :func:`find_portal_items`), reusing results of the last minutes.

    *query* builds the SPARQL query for a chunk of keys and returns
    ``(query, rows → {key: QID})``.  Returns ``({key: QID or None}, failed)``.
    '''
    cache_key = lambda key: f'mardmo_portal_{kind}_' + hashlib.sha1(json.dumps(key).encode('utf-8')).hexdigest()
    found, missing = {}, []
    for key in keys:
        cached = cache.get(cache_key(key))
        if cached is None:
            missing.append(key)
        else:
            found[key] = cached or None
    failed = False
    for start in range(0, len(missing), PORTAL_LOOKUP_CHUNK):
        chunk = missing[start:start + PORTAL_LOOKUP_CHUNK]
        sparql, parse = query(chunk)
        rows = query_sparql(sparql, get_url('mardi', 'sparql'), strict=True, waits=waits, deadline=deadline)
        if rows is None:
            failed = True
            continue
        matches = parse(rows)
        for key in chunk:
            # Several portal items: the lowest QID, the same each time
            qids = sorted(matches.get(key, ()), key=lambda qid: int(qid[1:]))
            found[key] = qids[0] if qids else None
            cache.set(cache_key(key), found[key] or '', PORTAL_LOOKUP_TIMEOUT)
    return found, failed


def find_portal_items(pairs=(), wikidata_qids=(), marker_qids=(), waits=(), deadline=None):
    '''Look up items on the MaRDI Portal: duplicates, Wikidata twins, and their markers (#141).

    - *pairs* ``(label, description)``: the portal item with exactly this
      English label and description, the rule the portal itself enforces
      (no case variants, no aliases).  Pairs without description are left
      out (new items need one anyway).
    - *wikidata_qids*: the portal item with this Wikidata QID (P12).
    - *marker_qids*: the ``instance of``, ``community`` and ``MaRDI profile
      type`` of these portal items (and of the items found).

    One read-only SPARQL query per :data:`PORTAL_LOOKUP_CHUNK` keys; the
    first two are cached for :data:`PORTAL_LOOKUP_TIMEOUT` seconds, also
    when nothing was found.

    Returns:
        :class:`PortalItems`.
    '''
    properties = get_properties()
    result = PortalItems()
    pairs = sorted({pair for pair in pairs
                    if pair[0] and pair[1] and pair[1] != 'No Description Provided!'})

    def by_label(chunk):
        values = ' '.join(f'({_sparql_literal(label)} {_sparql_literal(description)})'
                          for label, description in chunk)
        sparql = (f'SELECT ?item ?label ?description WHERE {{ VALUES (?label ?description) {{ {values} }} '
                  f'?item rdfs:label ?label ; schema:description ?description . }}')
        def parse(rows):
            matches = {}
            for row in rows:
                key = (row['label']['value'], row['description']['value'])
                matches.setdefault(key, []).append(row['item']['value'].rsplit('/', 1)[1])
            return matches
        return sparql, parse

    def by_wikidata(chunk):
        values = ' '.join(json.dumps(qid) for qid in chunk)
        sparql = (f'SELECT ?item ?wikidata WHERE {{ VALUES ?wikidata {{ {values} }} '
                  f'?item wdt:{properties["Wikidata QID"]} ?wikidata . }}')
        def parse(rows):
            matches = {}
            for row in rows:
                matches.setdefault(row['wikidata']['value'], []).append(row['item']['value'].rsplit('/', 1)[1])
            return matches
        return sparql, parse

    if pairs:
        result.by_label, result.label_failed = _cached_lookup('label', pairs, by_label, waits, deadline)
    qids = sorted({qid.split(':', 1)[-1] for qid in wikidata_qids})
    if qids:
        result.by_wikidata, result.wikidata_failed = _cached_lookup('wikidata', qids, by_wikidata, waits, deadline)

    # Markers of the given items and of the items found
    wanted = sorted({qid.split(':', 1)[-1] for qid in marker_qids}
                    | {qid for qid in (*result.by_label.values(), *result.by_wikidata.values()) if qid},
                    key=lambda qid: int(qid[1:]))
    for start in range(0, len(wanted), PORTAL_LOOKUP_CHUNK):
        chunk = wanted[start:start + PORTAL_LOOKUP_CHUNK]
        values = ' '.join(f'wd:{qid}' for qid in chunk)
        sparql = (f'SELECT ?item ?class ?community ?profile WHERE {{ VALUES ?item {{ {values} }} '
                  f'OPTIONAL {{ ?item wdt:{properties["instance of"]} ?class . }} '
                  f'OPTIONAL {{ ?item wdt:{properties["community"]} ?community . }} '
                  f'OPTIONAL {{ ?item wdt:{properties["MaRDI profile type"]} ?profile . }} }}')
        rows = query_sparql(sparql, get_url('mardi', 'sparql'), strict=True, waits=waits, deadline=deadline)
        if rows is None:
            result.markers_failed = True
            continue
        for qid in chunk:
            result.markers[qid] = {'class': set(), 'community': set(), 'profile': set()}
        for row in rows:
            markers = result.markers[row['item']['value'].rsplit('/', 1)[1]]
            for kind in ('class', 'community', 'profile'):
                if kind in row:
                    markers[kind].add(row[kind]['value'].rsplit('/', 1)[1])
    return result


def portal_labels(qids, waits=(), deadline=None):
    '''``{QID: (label, description)}`` (English) of the portal items *qids*; ``None`` if the query failed.

    For the preview of duplicates (#141): a Wikidata item found by its QID
    may have another label or description on the portal.
    '''
    labels = {}
    qids = sorted(set(qids), key=lambda qid: int(qid[1:]))
    for start in range(0, len(qids), PORTAL_LOOKUP_CHUNK):
        values = ' '.join(f'wd:{qid}' for qid in qids[start:start + PORTAL_LOOKUP_CHUNK])
        sparql = (f'SELECT ?item ?label ?description WHERE {{ VALUES ?item {{ {values} }} '
                  'OPTIONAL { ?item rdfs:label ?label . FILTER(LANG(?label) = "en") } '
                  'OPTIONAL { ?item schema:description ?description . FILTER(LANG(?description) = "en") } }')
        rows = query_sparql(sparql, get_url('mardi', 'sparql'), strict=True, waits=waits, deadline=deadline)
        if rows is None:
            return None
        for row in rows:
            labels[row['item']['value'].rsplit('/', 1)[1]] = (row.get('label', {}).get('value', ''),
                                                              row.get('description', {}).get('value', ''))
    return labels


def query_api(api_url, search_term, timeout=SEARCH_TIMEOUT, raise_errors=False, waits=(), deadline=None,
              limit=WIKIDATA_HITS):
    '''Search a Wikibase API endpoint for items whose label matches *search_term*.

    Uses the ``wbsearchentities`` action with at most *limit* hits (at most 50).

    Args:
        api_url:      Full URL of the Wikibase API endpoint.
        search_term:  Label string to search for.
        timeout:      Request timeout in seconds (default :data:`SEARCH_TIMEOUT`).
        raise_errors: Raise request and JSON errors instead of returning an
                      empty list, so callers can tell a failure from no hits.
        waits:        Pauses before retries (see :func:`request_with_retry`);
                      ``()`` searches once.
        deadline:     :func:`time.monotonic` value after which no retry starts.
        limit:        Number of hits asked for.

    Returns:
        List of raw Wikibase search-result dicts; empty list on any error
        (unless *raise_errors*).
    '''
    try:
        response = request_with_retry(
            'get',
            api_url,
            waits=waits,
            deadline=deadline,
            params={
                'action': 'wbsearchentities',
                'format': 'json',
                'language': 'en',
                'type': 'item',
                'limit': limit,
                'search': search_term
            },
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            timeout=timeout
        )
        response.raise_for_status()  # Raise an error on bad HTTP status codes
        try:
            return response.json().get('search', [])
        except ValueError:
            # Malformed JSON
            logger.error("Failed to parse JSON.")
            if raise_errors:
                raise
    except requests.exceptions.RequestException as e:
        logger.error("Search of %s failed: %s", api_url, e)
        if raise_errors:
            raise

    return []

def _cached_search(source, search, item_class, func):
    '''Return ``func(search)`` for *source*, reusing results from the last five minutes.

    Repeated searches — while typing, or for the same entity type on another
    page — then do not query the portal again.  The results do not depend on
    the project, so they cannot become outdated by the user's own answers.
    *func* must raise on request errors; a failed search returns no options
    and is not cached, so the next search tries again.
    '''
    classes = [item_class] if isinstance(item_class, str) else list(item_class or [])
    key = 'mardmo_search_' + hashlib.sha1(
        json.dumps([source, search, classes]).encode('utf-8')
    ).hexdigest()
    results = cache.get(key)
    if results is None:
        try:
            results = func(search)
        except (requests.exceptions.RequestException, ValueError):
            return []
        cache.set(key, results, SEARCH_CACHE_TIMEOUT)
    return results


# Wikidata's DOI property (the portal's is "DOI" in properties.json)
WIKIDATA_DOI = 'P356'
# The MaRDI Portal has some DOIs with "<" and ">" percent-encoded, as imported
# (10.1175/1520-0469(1963)020%3C0130:DNF%3E2.0.CO;2); it is searched for both
# forms.  "#" (the check character of old DOIs, "…3.0.CO;2-#") is encoded in
# links as well
_PORTAL_ENCODED = (('<', '%3C'), ('>', '%3E'), ('#', '%23'))


def portal_doi_forms(doi):
    '''The forms in which the MaRDI Portal may have *doi*: as it is, and percent-encoded if that differs.'''
    encoded = doi
    for character, code in _PORTAL_ENCODED:
        encoded = encoded.replace(character, code)
    return [doi] if encoded == doi else [doi, encoded]


def _portal_doi(stored):
    '''A DOI as the MaRDI Portal has it, in upper case and decoded (:func:`portal_doi_forms`).'''
    stored = stored.upper()
    for character, code in _PORTAL_ENCODED:
        stored = stored.replace(code, character)
    return stored


def _items_with_statement(source, statement):
    '''Options ``{id, text}`` of the items of *source* (``mardi``, ``wikidata``) with *statement* (``P27=10.…``).

    A search for the statement (``haswbstatement``, which ignores the case of
    a DOI), then the items' English labels and descriptions.  Raises on
    request errors (:func:`_cached_search` does not keep a failed search).
    '''
    api_url = get_url(source, 'api')
    headers = {'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'}
    found = request_with_retry(
        'get', api_url, waits=(SEARCH_RETRY_WAIT,), deadline=search_deadline(), headers=headers,
        timeout=SEARCH_TIMEOUT,
        params={'action': 'query', 'list': 'search', 'srsearch': f'haswbstatement:{statement}',
                'srnamespace': 120 if source == 'mardi' else 0, 'srlimit': 10, 'format': 'json'},
    )
    found.raise_for_status()
    qids = [hit['title'].rsplit(':', 1)[-1] for hit in found.json().get('query', {}).get('search', [])]
    if not qids:
        return []
    entities = request_with_retry(
        'get', api_url, waits=(SEARCH_RETRY_WAIT,), deadline=search_deadline(), headers=headers,
        timeout=SEARCH_TIMEOUT,
        params={'action': 'wbgetentities', 'ids': '|'.join(qids), 'props': 'labels|descriptions',
                'languages': 'en', 'format': 'json'},
    )
    entities.raise_for_status()
    entities = entities.json().get('entities', {})
    return [{'id': f'{source}:{qid}',
             'text': item_text(entities.get(qid, {}).get('labels', {}).get('en', {}).get('value', qid),
                               entities.get(qid, {}).get('descriptions', {}).get('en', {}).get(
                                   'value', 'No Description Provided!'))}
            for qid in qids]


def find_publications(doi):
    '''The publications with the DOI *doi*: ``(on the MaRDI Portal, on Wikidata)``, each a list of options.

    Both are searched at once; results are reused for five minutes
    (:func:`_cached_search`).  A source that does not answer finds nothing.
    '''
    statements = {'mardi': '|'.join(f"{get_properties()['DOI']}={form}" for form in portal_doi_forms(doi)),
                  'wikidata': f'{WIKIDATA_DOI}={doi.upper()}'}
    with ThreadPool(processes=2) as pool:
        mardi, wikidata = pool.map(
            lambda source: _cached_search(source, f'{DOI_PREFIX}{doi}', 'DOI',
                                          lambda _: _items_with_statement(source, statements[source])),
            ['mardi', 'wikidata'])
    return mardi, wikidata


def publication_options(search):
    '''The options of the publication dropdown for *search*, the identifier with its prefix (#158).

    Only an identifier is searched for (``doi:10.1000/x``), no title.  A
    publication on the MaRDI Portal is offered as the portal item only (the
    Wikidata item would be a duplicate), one only on Wikidata as the
    Wikidata item; one found nowhere as a new publication: the option is
    the identifier itself (ID ``new:doi:…``, tagged "new").  An identifier
    that is not valid is offered too, without asking anyone: saving it is
    refused with the reason (the pre-save validator), which the user would
    not learn from an empty dropdown.
    '''
    from .validators import doi_problem  # pylint: disable=import-outside-toplevel
    doi = publication_doi(search)
    if not doi:
        return []
    new = [{'id': f'{NEW_DOI}{doi}', 'text': f'{DOI_PREFIX}{doi}', 'help': option_help(NEW_DOI, f'{DOI_PREFIX}{doi}')}]
    if doi_problem(doi):
        return new
    mardi, wikidata = find_publications(doi)
    found = mardi or wikidata
    return [{**option, 'help': option_help(option['id'], option['text'])} for option in found] if found else new


# The lookups of publication twins while a page is filled (#158): requests are
# given up after this many seconds and retried once; wbgetentities takes at
# most 50 items, a search for DOIS_PER_SEARCH DOIs finds at most 50 items
TWIN_TIMEOUT = 10
ENTITIES_PER_REQUEST = 50
DOIS_PER_SEARCH = 20


def _entities(source, qids, props, waits=(SEARCH_RETRY_WAIT,), deadline=None):
    '''``{QID: entity}`` of *qids* on *source* (``wbgetentities``, English labels); raises on request errors.'''
    entities = {}
    for start in range(0, len(qids), ENTITIES_PER_REQUEST):
        response = request_with_retry(
            'get', get_url(source, 'api'), waits=waits, deadline=deadline, timeout=TWIN_TIMEOUT,
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            params={'action': 'wbgetentities', 'ids': '|'.join(qids[start:start + ENTITIES_PER_REQUEST]),
                    'props': props, 'languages': 'en', 'format': 'json'})
        response.raise_for_status()
        entities.update(response.json().get('entities', {}))
    return entities


def _claim_values(entity, prop):
    '''The string values of the statements *prop* of *entity* (from ``wbgetentities``).'''
    return [claim['mainsnak']['datavalue']['value'] for claim in entity.get('claims', {}).get(prop, [])
            if claim.get('mainsnak', {}).get('snaktype') == 'value'
            and isinstance(claim['mainsnak']['datavalue']['value'], str)]


def _by_qid(qids):
    '''*qids* (``Q1``) in the order of their numbers.'''
    return sorted(qids, key=lambda qid: int(qid[1:]))


def wikidata_dois(qids):
    '''``{QID: DOI}`` of the Wikidata items *qids* that have a DOI (P356; the first one).

    One ``wbgetentities`` request per :data:`ENTITIES_PER_REQUEST` items.  A
    lookup that fails finds no DOIs.
    '''
    qids = sorted(set(qids))
    if not qids:
        return {}
    try:
        entities = _entities('wikidata', qids, 'claims')
    except (requests.exceptions.RequestException, ValueError) as error:
        logger.warning('Could not look up the DOIs of Wikidata publications: %s', error)
        return {}
    # Some have their DOI with a leading "/"
    return {qid: dois[0].lstrip('/') for qid in qids if (dois := _claim_values(entities.get(qid, {}), WIKIDATA_DOI))}


def find_publications_by_doi(dois, waits=(SEARCH_RETRY_WAIT,), deadline=None):
    '''``{DOI in upper case: (QID, label, description)}`` of the MaRDI Portal's publications with *dois*.

    One search (``haswbstatement`` with alternatives, which ignores the case
    of a DOI; both forms of :func:`portal_doi_forms`) per
    :data:`DOIS_PER_SEARCH` DOIs, then the items found, whose
    DOIs say which DOI each one has.  Of several items with a DOI the one
    with the lowest QID; items without English label are left out.

    Raises:
        requests.exceptions.RequestException, ValueError: if the portal did
            not answer (the duplicate check must know).
    '''
    dois = sorted({doi.upper() for doi in dois if doi})
    if not dois:
        return {}
    prop = get_properties()['DOI']
    qids = set()
    for start in range(0, len(dois), DOIS_PER_SEARCH):
        statements = '|'.join(f'{prop}={form}' for doi in dois[start:start + DOIS_PER_SEARCH]
                              for form in portal_doi_forms(doi))
        response = request_with_retry(
            'get', get_url('mardi', 'api'), waits=waits, deadline=deadline, timeout=TWIN_TIMEOUT,
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            params={'action': 'query', 'list': 'search', 'srsearch': f'haswbstatement:{statements}',
                    'srnamespace': 120, 'srlimit': 50, 'srprop': '', 'format': 'json'})
        response.raise_for_status()
        qids |= {hit['title'].rsplit(':', 1)[-1] for hit in response.json().get('query', {}).get('search', [])}
    entities = _entities('mardi', _by_qid(qids), 'claims|labels|descriptions', waits, deadline) if qids else {}
    wanted, found = set(dois), {}
    for qid in _by_qid(entities):
        entity = entities[qid]
        label = entity.get('labels', {}).get('en', {}).get('value')
        if not label:
            continue
        description = entity.get('descriptions', {}).get('en', {}).get('value', 'No Description Provided!')
        for doi in _claim_values(entity, prop):
            if _portal_doi(doi) in wanted:
                found.setdefault(_portal_doi(doi), (qid, label, description))
    return found


def portal_publications_by_doi(dois):
    ''':func:`find_publications_by_doi`, but a lookup that fails finds nothing (filling pages, #158).'''
    try:
        return find_publications_by_doi(dois)
    except (requests.exceptions.RequestException, ValueError) as error:
        logger.warning('Could not look up publications on the MaRDI Portal by DOI: %s', error)
        return {}


def portal_dois(qids, waits=(SEARCH_RETRY_WAIT,), deadline=None):
    '''``{QID: {DOIs in upper case}}`` of the MaRDI Portal items *qids*; raises if the portal did not answer.'''
    qids = _by_qid(set(qids))
    if not qids:
        return {}
    prop = get_properties()['DOI']
    entities = _entities('mardi', qids, 'claims', waits, deadline)
    return {qid: {_portal_doi(doi) for doi in _claim_values(entities.get(qid, {}), prop)} for qid in qids}


def _label_description(option):
    '''Return ``(label, description)`` of an option, to offer a Wikidata hit only once.

    The label is compared case-insensitively, the description exactly.
    Options without a description give ``None``: a matching label alone
    does not make two items the same.
    '''
    label, description, _ = extract_parts(option['text'])
    if not description or description == 'No Description Provided!':
        return None
    return label.strip().lower(), description.strip()


def wikidata_hits(hits, roots, noise=None):
    '''The Wikidata search *hits* that are at or below *roots*, in their order (#170).

    With *noise* instead of *roots*, those that are not an instance of one of
    its classes.  Without either, or if the check of their classes fails,
    the first :data:`WIKIDATA_HITS` hits, unfiltered, as before the check.
    '''
    if roots is None and noise is None:
        return hits[:WIKIDATA_HITS]
    matches = wikidata_matches([hit['id'] for hit in hits if 'id' in hit], roots=roots,
                               noise=None if roots is not None else noise)
    if matches is None:
        return hits[:WIKIDATA_HITS]
    return [hit for hit in hits if matches.get(hit.get('id'))]


def query_sources(search, item_class=None, sources=None, not_found=True, roots=None, noise=None, profiles=None,
                  exclude=None):
    '''Query one or more knowledge-graph sources for items matching *search*.

    Queries the requested sources in parallel (results are cached for five
    minutes, see :func:`_cached_search`), merges the results, and sorts them by
    relevance to *search* using :func:`~.queries.rank_by_search_term`.
    A Wikidata result with the same label and description as a MaRDI result
    is left out: it is the same item, and the export would ask the user to
    select the MaRDI one.

    Args:
        search:     Free-text search string.
        item_class: QID string or list of QID strings used for class-filtered
                    search on MaRDI (e.g. ``"Q42"`` or ``["Q42", "Q43"]``);
                    the classes without a MaRDI profile, where *profiles* is given.
        sources:    List of source keys to query; defaults to
                    ``["mardi", "wikidata"]``.
        not_found:  If ``True`` (default), prepends the option ``{"id": "not found",
                    "text": "new item"}`` to the option list.
        roots:      Wikidata classes the Wikidata hits must be at or below
                    (:func:`wikidata_hits`); ``None``: Wikidata is searched by
                    label only, as before.
        noise:      Instead of *roots* (where no class fits): Wikidata classes
                    the Wikidata hits must not be instances of.
        profiles:   QIDs of MaRDI profiles whose items are searched on the
                    portal (:func:`query_api_per_profile`), in parallel with
                    the class search of *item_class* if there is one.
        exclude:    QIDs of classes whose items the profile search leaves out.

    Returns:
        List of ``{"id": …, "text": "Label (Description)", "help": source tag}``
        option dicts, sorted by relevance; "new item" has no help.
    '''
    if sources is None:
        sources = ['mardi', 'wikidata']

    source_functions = {}
    if 'mardi' in sources:
        if item_class or not profiles:
            source_functions['mardi'] = lambda s: _cached_search(
                'mardi', s, item_class, lambda t: query_api_per_class(t, item_class, raise_errors=True))
        if profiles:
            # The items with a profile (most have no class), in parallel (#170);
            # the cached results depend on the classes left out, too
            scope = list(profiles) + [f'not:{qid}' for qid in exclude or []]
            source_functions['mardi-profiles'] = lambda s: _cached_search(
                'mardi-profiles', s, scope, lambda t: query_api_per_profile(t, profiles, exclude, raise_errors=True))
    if 'wikidata' in sources:
        # One search for all dropdowns (its first hits are those of a shorter
        # one); each filters them by its classes, in parallel with the portal
        source_functions['wikidata'] = lambda s: wikidata_hits(_cached_search(
            'wikidata', s, None, lambda t: query_api(get_url('wikidata', 'api'), t, raise_errors=True,
                                                     waits=(SEARCH_RETRY_WAIT,), deadline=search_deadline(),
                                                     limit=WIKIDATA_FILTERED_HITS)), roots, noise)

    # Runs on every autocomplete search; close the pool so threads do not pile up
    with ThreadPool(processes=len(source_functions)) as pool:
        results = pool.map(lambda func: func(search), source_functions.values())
    results_dict = dict(zip(source_functions.keys(), results))
    if 'mardi-profiles' in results_dict:
        # Taken in turns, so that the first 25 have hits of both searches
        merged = {}
        for pair in zip_longest(results_dict.get('mardi', []), results_dict.pop('mardi-profiles')):
            merged.update({option['id']: option for option in pair if option and option['id'] not in merged})
        results_dict['mardi'] = list(merged.values())

    options = []
    for source in sources:
        if source not in results_dict:
            continue
        raw = results_dict[source][:25]
        if source == 'wikidata':
            # query_api returns raw Wikibase search dicts; format them here
            display_key = 'display'
            raw = [
                {
                    'id':   f"wikidata:{r['id']}",
                    'text': (f"{r[display_key].get('label', {}).get('value', 'No Label Provided!')}"
                             f" ({r[display_key].get('description', {}).get('value', 'No Description Provided!')})"),
                }
                for r in raw
                if display_key in r
            ]
        options += raw

    # A Wikidata item with the label and description of a MaRDI item is that
    # item; offer only the MaRDI one, the export would ask to select it anyway
    mardi_items = {_label_description(opt) for opt in options if opt['id'].startswith('mardi:')}
    mardi_items.discard(None)
    options = [opt for opt in options
               if not (opt['id'].startswith('wikidata:') and _label_description(opt) in mardi_items)]

    options.sort(key=lambda opt: rank_by_search_term(opt, search))
    # The source is shown grey in the open dropdown, not stored (#103)
    options = [{**option, 'help': option_help(option['id'], option['text'])} for option in options]

    if not_found:
        options = [{'id': NOT_FOUND, 'text': NEW_ITEM}] + options

    return options

def query_sources_with_user_additions(search, project, setup):
    '''Fetch KG options, prepend matching user-defined entries, and optionally allow creation.

    Combines external source results (via :func:`query_sources`) with entries
    the user has already added to the questionnaire.  These are read from the
    database on every call, so entries saved a moment ago are offered too.
    Optionally inserts a creation option for new entries.

    Args:
        search:  Free-text search string entered by the user.
        project: RDMO project instance used to look up existing user entries.
        setup:   Configuration dict with keys:

                 * ``sources``          – list of source keys (default
                   ``["mardi", "wikidata"]`` when ``None``)
                 * ``item_class``       – QID or list of QIDs for class filtering
                 * ``query_attributes`` – list of attribute URI fragments to
                   query for user-defined entries
                 * ``creation``         – bool; if ``True``, prepend an option
                   that lets users create a new entry with the search text
                 * ``answer_class``     – MathModDB class key (``Quantity`` or
                   ``QuantityKind``) the user's own quantities must have;
                   quantities without a class yet are offered too
                 * ``roots``            – Wikidata classes the Wikidata hits
                   must be at or below (``None``: not filtered)
                 * ``noise``            – instead of roots: Wikidata classes
                   the Wikidata hits must not be instances of
                 * ``profiles``, ``exclude`` – MaRDI profiles whose items the
                   portal search finds too, classes whose items it leaves out

    Returns:
        List of ``{"id": …, "text": …}`` option dicts.
    '''
    if setup['sources'] is None:
        setup['sources'] = ['mardi', 'wikidata']

    # Query external sources
    try:
        options = query_sources(
            search=search,
            item_class=setup['item_class'],
            sources=setup['sources'],
            not_found=False,
            roots=setup.get('roots'),
            noise=setup.get('noise'),
            profiles=setup.get('profiles'),
            exclude=setup.get('exclude'),
        )
    except (requests.exceptions.RequestException, KeyError, ValueError, TypeError) as e:
        logger.error("Query sources failed: %s", e)
        options = []

    if setup.get('query_attributes'):
        try:
            options_user = query_user_entries(project, setup)
        except Exception as e:
            logger.error("User entries query failed: %s", e)
            options_user = []

        # Filter and merge options
        options = [option for option in options_user if search.lower() in option['text'].lower()] + options

    # Add creation option if needed
    if setup['creation']:
        if not any(option['id'] == NOT_FOUND and option['text'] == search for option in options):
            options.insert(0, {'id': NOT_FOUND, 'text': search, 'help': option_help(NOT_FOUND, search)})

    return options

def query_user_entries(project, setup):
    '''Return the options of the items the user has already added to the questionnaire.

    Reads the ID, Name, and Description values of all attributes listed in
    ``setup["query_attributes"]`` with two database queries, aligns them by
    ``set_index``/``set_prefix``, and returns only entries whose source is not
    in ``setup["sources"]`` (i.e. not already covered by KG results).  With
    ``setup["answer_class"]``, quantities of the other class are left out.

    Args:
        project: RDMO project instance.
        setup:   Configuration dict (see :func:`query_sources_with_user_additions`).

    Returns:
        List of ``{"id": …, "text": "Label (Description)", "help": source tag}``
        options (:func:`option_help`).
    '''
    uris = {
        f'{BASE_URI}domain/{query_attribute}/{question}': (query_attribute, question)
        for query_attribute in setup['query_attributes']
        for question in ('id', 'name', 'description')
    }
    wanted_class = None
    if setup.get('answer_class'):
        uris[f'{BASE_URI}domain/quantity/is-quantity-or-quantity-kind'] = ('quantity', 'class')
        wanted_class = get_mathmoddb().get(key=setup['answer_class'])['url']
    attributes = {
        attribute.id: uris[attribute.uri]
        for attribute in Attribute.objects.filter(uri__in=uris)
    }

    # Align id/name/description per entity type and entity index
    entries = {}
    for value in project.values.filter(snapshot=None, attribute_id__in=attributes).select_related('option'):
        query_attribute, question = attributes[value.attribute_id]
        idx = value.set_index if question in ('id', 'class') else int(value.set_prefix)
        entries.setdefault((setup['query_attributes'].index(query_attribute), idx), {})[question] = value

    options = []
    for _, entry in sorted(entries.items()):
        if 'id' not in entry or not entry['id'].text:
            continue
        # Quantity of the other class; without a class yet it is offered
        if entry.get('class') and entry['class'].option and entry['class'].option.uri != wanted_class:
            continue
        if not is_item_id(entry['id'].external_id):
            # No real ID (made before MaRDMO 0.8.0): reported by the checks
            continue
        # Offered with the ID, name and description of its page (as preview
        # and export show it); a portal page not filled yet by its ID's text
        name, description = entry.get('name'), entry.get('description')
        name, description = (name.text if name else ''), (description.text if description else '')
        if not name and not is_user_id(entry['id'].external_id):
            name, description, _ = extract_parts(entry['id'].text)
        label = name or "No Label Provided!"
        description = description or "No Description Provided!"
        item_id = entry['id'].external_id
        # Only the sources the dropdown does not search
        if item_id.split(':', 1)[0] not in setup['sources']:
            options.append({'id': item_id, 'text': item_text(label, description),
                            'help': option_help(item_id, item_text(label, description))})
    return options

def query_api_per_class(search_term: str, item_class, raise_errors: bool = False) -> list[dict]:
    '''Search the MaRDI portal for items belonging to one or more Wikibase classes.

    Performs a MediaWiki full-text search filtered by
    ``haswbstatement:<instance-of>=QID`` (combined with ``|`` for multiple
    classes), then fetches English labels and descriptions for the matching
    QIDs via ``wbgetentities``.  The "instance of" property ID is read from
    the configured ``properties.json`` so it works across portals.

    Args:
        search_term: Free-text search string (appended with ``*`` for prefix matching).
        item_class:  QID string or list of QID strings; e.g. ``"Q42"`` or
                     ``["Q42", "Q43"]``.
        raise_errors: Raise request errors instead of returning an empty list,
                     so callers can tell a failure from no hits.

    Returns:
        List of ``{"id": "mardi:<QID>", "text": "Label (Description)"}``
        dicts; empty list on any network error (unless *raise_errors*) or no hits.
    '''
    if isinstance(item_class, str):
        item_class = [item_class]

    instance_of  = get_properties()['instance of']
    class_filter = '|'.join(f'{instance_of}={qid}' for qid in item_class)
    try:
        search_resp = request_with_retry(
            'get',
            get_url('mardi', 'api'),
            waits=(SEARCH_RETRY_WAIT,),
            deadline=search_deadline(),
            params={
                'action':      'query',
                'list':        'search',
                'srsearch':    f'{search_term}* haswbstatement:{class_filter}',
                'srnamespace': 120,
                'srlimit':     50,
                'srprop':      'snippet',
                'format':      'json',
            },
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            timeout=SEARCH_TIMEOUT,
        )
        search_resp.raise_for_status()
        hits = search_resp.json().get('query', {}).get('search', [])
    except requests.exceptions.RequestException as e:
        logger.error("Class-based MaRDI search failed: %s", e)
        if raise_errors:
            raise
        return []

    return _portal_options([hit['title'].removeprefix('Item:') for hit in hits], raise_errors)


def query_api_per_profile(search_term, profiles, exclude=None, raise_errors=False):
    '''Search the MaRDI portal for items with one of the MaRDI *profiles* (#170).

    The portal's faceted search (``haswbfacet:<profile type>=QID``, several
    as alternatives) finds the profile pages, also of the many items without
    a class (most software); each page names its item (page property
    ``wikibase_item``).  The values of the profile type are not indexed for
    ``haswbstatement``, so this is the portal's own way.  Items of a class of
    *exclude* (another class with the same profile) are left out.

    Args:
        search_term: Free-text search string (appended with ``*`` for prefix matching).
        profiles:    QIDs of MaRDI profiles.
        exclude:     QIDs of classes whose items are left out.
        raise_errors: Raise request errors instead of returning an empty list.

    Returns:
        Option dicts as :func:`query_api_per_class` returns them.
    '''
    profile_type = get_properties()['MaRDI profile type']
    facets = ' '.join(f'haswbfacet:{profile_type}={qid}' for qid in profiles)
    try:
        response = request_with_retry(
            'get',
            get_url('mardi', 'api'),
            waits=(SEARCH_RETRY_WAIT,),
            deadline=search_deadline(),
            params={
                'action':       'query',
                'generator':    'search',
                'gsrsearch':    f'{search_term}* {facets}',
                'gsrnamespace': 0,
                'gsrlimit':     50,
                'prop':         'pageprops',
                'ppprop':       'wikibase_item',
                'format':       'json',
            },
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            timeout=SEARCH_TIMEOUT,
        )
        response.raise_for_status()
        pages = response.json().get('query', {}).get('pages', {}).values()
    except requests.exceptions.RequestException as e:
        logger.error("Profile-based MaRDI search failed: %s", e)
        if raise_errors:
            raise
        return []

    # In the order of the search; a page without an item is left out
    ranked = sorted(pages, key=lambda page: page.get('index', 0))
    qids = list(dict.fromkeys(page['pageprops']['wikibase_item'] for page in ranked
                              if page.get('pageprops', {}).get('wikibase_item')))
    return _portal_options(qids, raise_errors, exclude)


def _portal_options(qids, raise_errors=False, exclude=None):
    '''The options of the portal items *qids*, with their English labels and descriptions.

    With *exclude*, their classes are fetched too, and the items of one of
    these classes are left out.
    '''
    if not qids:
        return []
    try:
        entity_resp = request_with_retry(
            'get',
            get_url('mardi', 'api'),
            waits=(SEARCH_RETRY_WAIT,),
            deadline=search_deadline(),
            params={
                'action':    'wbgetentities',
                'ids':       '|'.join(qids),
                'props':     'labels|descriptions|claims' if exclude else 'labels|descriptions',
                'languages': 'en',
                'format':    'json',
            },
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            timeout=SEARCH_TIMEOUT,
        )
        entity_resp.raise_for_status()
        entities = entity_resp.json().get('entities', {})
    except requests.exceptions.RequestException as e:
        logger.error("MaRDI entity fetch failed: %s", e)
        if raise_errors:
            raise
        return []

    instance_of = get_properties()['instance of']
    results = []
    for qid in qids:
        entity      = entities.get(qid, {})
        if exclude and _classes(entity, instance_of) & set(exclude):
            continue
        label       = entity.get('labels',       {}).get('en', {}).get('value', qid)
        description = entity.get('descriptions', {}).get('en', {}).get('value',
                                                                        'No Description Provided!')
        results.append({
            'id':   f'mardi:{qid}',
            'text': item_text(label, description),
        })

    return results


def _classes(entity, instance_of):
    '''The QIDs of the classes (*instance_of* statements) of a ``wbgetentities`` *entity*.'''
    return {claim['mainsnak'].get('datavalue', {}).get('value', {}).get('id')
            for claim in entity.get('claims', {}).get(instance_of, [])}


# A search text that names an item, ``mardi:Q123`` or ``wikidata:Q42``; the
# prefix in any case, spaces around the colon allowed (#170)
TYPED_ITEM_ID = re.compile(r'\s*(mardi|wikidata)\s*:\s*(q[1-9][0-9]*)\s*', re.IGNORECASE)


def typed_item_id(search):
    '''``(source, QID)`` if *search* names an item (:data:`TYPED_ITEM_ID`), else ``None``.'''
    match = TYPED_ITEM_ID.fullmatch(search or '')
    return (match[1].lower(), match[2].upper()) if match else None


def item_by_id(source, qid, classes=None, profiles=None, exclude=None, roots=None, noise=None):
    '''The option of the item *qid* of *source* named in a dropdown, if it fits it; ``[]`` otherwise (#170).

    The item fits as a search hit would: on the portal if it is of one of
    *classes* or has one of *profiles* and is not of a class of *exclude*; on
    Wikidata if it is at or below *roots* or not of a class of *noise*
    (:mod:`~MaRDMO.class_check`; if the check fails, as unfiltered hits do).
    A merged item is offered as the item it was merged into; an item that
    does not exist is not offered.

    Args:
        source:   ``'mardi'`` or ``'wikidata'``.
        qid:      The item's QID.
        classes:  QIDs of the dropdown's portal classes (all of them).
        profiles: QIDs of the MaRDI profiles of its classes.
        exclude:  QIDs of classes whose items it leaves out.
        roots:    Wikidata classes its Wikidata hits must be at or below.
        noise:    Instead of *roots*: Wikidata classes they must not be instances of.

    Returns:
        ``[option]`` or ``[]``.
    '''
    try:
        entities = _entities(source, [qid], 'labels|descriptions|claims' if source == 'mardi'
                             else 'labels|descriptions', deadline=search_deadline())
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Lookup of %s:%s failed: %s", source, qid, e)
        return []
    entity = entities.get(qid) or next(iter(entities.values()), {})
    if not entity or 'missing' in entity:
        return []
    # wbgetentities answers a merged item with the one it was merged into
    target = entity.get('id', qid)

    if source == 'mardi':
        properties = get_properties()
        found = _classes(entity, properties['instance of'])
        if not (found & set(classes or []) or _classes(entity, properties['MaRDI profile type']) & set(profiles or [])):
            return []
        if found & set(exclude or []):
            return []
    elif roots is not None or noise is not None:
        matches = wikidata_matches([target], roots=roots, noise=None if roots is not None else noise)
        if matches is not None and not matches.get(target):
            return []

    label = entity.get('labels', {}).get('en', {}).get('value', target)
    description = entity.get('descriptions', {}).get('en', {}).get('value', 'No Description Provided!')
    item_id, text = f'{source}:{target}', item_text(label, description)
    return [{'id': item_id, 'text': text, 'help': option_help(item_id, text)}]


def rank_by_search_term(option, term):
    '''Return a numeric sort key indicating how well *option* matches *term*.

    Lower values sort first (better match):

    * 0 – label is exact match
    * 1 – label starts with term
    * 2 – label contains term
    * 3 – description contains term
    * 4 – no match

    Args:
        option: Option dict with a ``text`` field in
                ``"Label (Description)"`` format.
        term:   Search string entered by the user.

    Returns:
        Integer rank value 0–4.
    '''
    label, desc, _ = extract_parts(option['text'])
    label_lower = label.lower()
    term_lower  = term.lower()
    if label_lower == term_lower:
        return 0
    if label_lower.startswith(term_lower):
        return 1
    if term_lower in label_lower:
        return 2
    if term_lower in desc.lower():
        return 3
    return 4


# The source of an option (#142): the word of its badge, by the prefix of its ID, with
# the badge's background and text colours (light, with the word: colour alone is not
# accessible)
_SOURCE_TAGS = {'mardi': 'mardi', 'wikidata': 'wikidata', 'user': 'project', 'new': 'new', NOT_FOUND: 'new'}
_BADGES = {'mardi': ('#dbe9ff', '#1a3d7c'), 'wikidata': ('#dcf3e3', '#1e5e33'),
           'project': ('#fff1cc', '#7a5a00'), 'new': ('#ece3fb', '#4b2c83')}
# Hides the plain text of a laid-out option (RDMO shows the text, then the help); a browser
# without :has() shows both, the text stays readable
_HIDE_TEXT = ('<style>.interview-select-option:has(.mardmo-option) > span:first-child {display: none}'
              '.interview-select-option:has(.mardmo-option) > span.ml-10 {margin-left: 0}</style>')


def option_help(identifier, text):
    '''Return the help of a dropdown option for the item *identifier* with the text *text*: its layout (#142).

    A badge with the source (``mardi``, ``wikidata``, ``project`` for an
    item of the user's own in the project, ``new`` for a new item: typed in
    a relation, ``not found``, or a new publication, ``new:doi:…``), the
    label in bold and the description in grey italics on a second line.
    RDMO renders the help of an option as HTML in the open dropdown only,
    after its text; a CSS rule hides the text there.  The text stays
    ``"Label (Description)"``: it is what RDMO stores and shows in the
    filled field, and what screen readers announce.  ``''`` for an option
    without source (e.g. "new item").
    '''
    tag = _SOURCE_TAGS.get((identifier or '').split(':', 1)[0])
    if not tag or (identifier == NOT_FOUND and text == NEW_ITEM):
        return ''
    background, colour = _BADGES[tag]
    label, description, _ = extract_parts(text or '')
    layout = (f'<span class="mardmo-option"><span style="display:inline-block;background:{background};'
              f'color:{colour};border-radius:3px;padding:0 5px;margin-right:6px;font-size:80%;'
              f'vertical-align:1px">{tag}</span><span style="font-weight:600">{html.escape(label)}</span>')
    if description and description != 'No Description Provided!':
        layout += (f'<br><span style="color:#6c757d;font-style:italic;font-size:90%;margin-left:2px">'
                   f'{html.escape(description)}</span>')
    return f'{_HIDE_TEXT}{layout}</span>'
