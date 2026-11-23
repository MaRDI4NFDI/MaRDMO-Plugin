'''The MaRDI Portal: its items, their markers and twins, its search, its publications (#198).

- :func:`find_portal_items`, :func:`portal_labels` — duplicates, Wikidata
  twins and markers of items on the portal (SPARQL, #141);
- :func:`query_api_per_class`, :func:`query_api_per_profile` — the portal's
  search for the items of classes or MaRDI profiles (#170);
- :func:`find_publications_by_doi`, :func:`portal_dois` — publications on
  the portal by their DOI (#158).
'''
import hashlib
import json
import logging
from dataclasses import dataclass, field

import requests
from django.core.cache import cache

from ..getters import get_properties, get_url
from ..ids import item_text
from .http import SEARCH_RETRY_WAIT, SEARCH_TIMEOUT, query_sparql, request_with_retry, search_deadline
from .wikibase import TWIN_TIMEOUT, claim_values, entities_of, entity_classes, get_entities

logger = logging.getLogger(__name__)


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


DOIS_PER_SEARCH = 20


def _by_qid(qids):
    '''*qids* (``Q1``) in the order of their numbers.'''
    return sorted(qids, key=lambda qid: int(qid[1:]))


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
    entities = entities_of('mardi', _by_qid(qids), 'claims|labels|descriptions', waits, deadline) if qids else {}
    wanted, found = set(dois), {}
    for qid in _by_qid(entities):
        entity = entities[qid]
        label = entity.get('labels', {}).get('en', {}).get('value')
        if not label:
            continue
        description = entity.get('descriptions', {}).get('en', {}).get('value', 'No Description Provided!')
        for doi in claim_values(entity, prop):
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
    entities = entities_of('mardi', qids, 'claims', waits, deadline)
    return {qid: {_portal_doi(doi) for doi in claim_values(entities.get(qid, {}), prop)} for qid in qids}


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
        entities = get_entities(get_url('mardi', 'api'), qids,
                                'labels|descriptions|claims' if exclude else 'labels|descriptions',
                                languages='en', waits=(SEARCH_RETRY_WAIT,), deadline=search_deadline(),
                                timeout=SEARCH_TIMEOUT)
    except requests.exceptions.RequestException as e:
        logger.error("MaRDI entity fetch failed: %s", e)
        if raise_errors:
            raise
        return []

    instance_of = get_properties()['instance of']
    results = []
    for qid in qids:
        entity      = entities.get(qid, {})
        if exclude and entity_classes(entity, instance_of) & set(exclude):
            continue
        label       = entity.get('labels',       {}).get('en', {}).get('value', qid)
        description = entity.get('descriptions', {}).get('en', {}).get('value',
                                                                        'No Description Provided!')
        results.append({
            'id':   f'mardi:{qid}',
            'text': item_text(label, description),
        })

    return results
