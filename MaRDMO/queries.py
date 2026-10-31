'''Functions that query external data sources (Wikibase API, SPARQL endpoints, Crossref, etc.).

Provides helpers for:

* ``query_item`` / ``query_api`` – Wikibase ``wbsearchentities`` lookups
* ``query_sparql`` / ``query_sparql_pool`` – SPARQL SELECT requests
* ``query_sparql_parts`` – run the split parts of a query and merge their rows
* ``sparql_string`` – escape text as a SPARQL string literal
* ``query_sources`` / ``query_sources_with_user_additions`` – combined
  MaRDI + Wikidata search with optional user-defined entries
* ``query_api_per_class`` – class-filtered full-text search on the MaRDI portal
* ``http_session`` – shared HTTP session for all requests to external services
'''
import hashlib
import json
import logging
import threading
import time
from multiprocessing.pool import ThreadPool

import requests
from django.core.cache import cache
from rdmo.domain.models import Attribute

from .constants import BASE_URI
from .getters import get_properties, get_url
from .helpers import commit_writes, extract_parts, rank_by_search_term

logger = logging.getLogger(__name__)

# Search results of the MaRDI Portal and Wikidata are reused for this long
SEARCH_CACHE_TIMEOUT = 5 * 60

# A SPARQL query is given up after this many seconds and retried once on a
# timeout, a connection error or one of these answers, after the portal's
# Retry-After (at most SPARQL_MAX_RETRY_WAIT seconds) or SPARQL_RETRY_WAIT
SPARQL_TIMEOUT = 30
SPARQL_RETRY_STATUS = (429, 502, 503, 504)
SPARQL_RETRY_WAIT = 2
SPARQL_MAX_RETRY_WAIT = 10

_SESSIONS = threading.local()


def http_session():
    '''Return this thread's HTTP session for requests to external services.

    Reusing the session keeps connections open, so repeated requests to the
    same service skip the connection setup.  MaRDMO's pending writes are
    committed first (see :func:`~MaRDMO.helpers.batched_writes`), so no
    transaction stays open while waiting for the answer.
    '''
    commit_writes()
    session = getattr(_SESSIONS, 'session', None)
    if session is None:
        session = _SESSIONS.session = requests.Session()
    return session


def query_item(label, description, api = get_url('mardi', 'api')):
    '''Search a Wikibase API for an item matching *label* and *description* exactly.

    Skips the request if *description* is empty or the placeholder string
    ``"No Description Provided!"``.

    Args:
        label:       Label (or alias) to search for (case-insensitive).
        description: Exact description the matched item must have.
        api:         Wikibase ``wbsearchentities`` API URL; defaults to MaRDI Portal.

    Returns:
        The Wikibase QID string of the first match, or ``None`` if no match.
    '''
    # Only check Items with description
    if not description or description == 'No Description Provided!':
        return None

    # Get data from API
    data = query_api(api, label)

    # Normalize input label for comparison (case insensitive)
    norm_label = label.strip().lower()

    matched_items = []
    for item in data:
        item_label = item.get('label', '').strip().lower()
        item_description = item.get('description', '').strip()
        item_aliases = [alias.strip().lower() for alias in item.get('aliases', [])]

        # Check label or alias match AND description match
        if (
            (item_label == norm_label or norm_label in item_aliases)
            and item_description == description
        ):
            matched_items.append(item)

    if matched_items:
        return matched_items[0]['id']

    return None

def query_api(api_url, search_term, timeout=5, raise_errors=False):
    '''Search a Wikibase API endpoint for items whose label matches *search_term*.

    Uses the ``wbsearchentities`` action with ``limit=10``.

    Args:
        api_url:      Full URL of the Wikibase API endpoint.
        search_term:  Label string to search for.
        timeout:      Request timeout in seconds (default 5).
        raise_errors: Raise request and JSON errors instead of returning an
                      empty list, so callers can tell a failure from no hits.

    Returns:
        List of raw Wikibase search-result dicts; empty list on any error
        (unless *raise_errors*).
    '''
    try:
        response = http_session().get(
            api_url,
            params={
                'action': 'wbsearchentities',
                'format': 'json',
                'language': 'en',
                'type': 'item',
                'limit': 10,
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
        logger.error("Request failed due to %s", e)
        if raise_errors:
            raise

    return []

def sparql_string(value):
    '''Return *value* as a double-quoted SPARQL string literal.

    Escapes backslashes, quotes, and line breaks so that arbitrary user text
    (multi-line descriptions, Windows paths, LaTeX, apostrophes) yields a
    valid query.
    '''
    escaped = (
        str(value)
        .replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\n', '\\n')
        .replace('\r', '\\r')
        .replace('\t', '\\t')
    )
    return f'"{escaped}"'

def query_sparql(query, sparql_endpoint, strict=False):
    '''Execute a SPARQL SELECT query against *sparql_endpoint* and return bindings.

    Args:
        query:           SPARQL SELECT query string (UTF-8 encoded on the wire).
        sparql_endpoint: URL of the SPARQL endpoint (e.g. the MaRDI or Wikidata endpoint).
        strict:          If ``True``, return ``None`` instead of ``[]`` when the
                         query fails, so callers can tell "failed" from "no results".

    A query that times out (after :data:`SPARQL_TIMEOUT` seconds), cannot
    connect, or is answered with one of :data:`SPARQL_RETRY_STATUS` is
    retried once.

    Returns:
        List of result-binding dicts from ``results.bindings``; on any network
        error, HTTP error, invalid answer, or missing endpoint an empty list
        (or ``None`` with *strict*).
    '''
    failed = None if strict else []

    if not sparql_endpoint:
        logger.warning("SPARQL query attempted without a valid endpoint.")
        return failed

    for attempt in (1, 2):
        retry_after = None
        try:
            response = http_session().post(
                sparql_endpoint,
                data=query.encode("utf-8"),
                headers={
                    "User-Agent": "MaRDMO (https://zib.de; reidelbach@zib.de)",
                    "Content-Type": "application/sparql-query; charset=UTF-8",
                    "Accept": "application/sparql-results+json"
                },
                timeout = SPARQL_TIMEOUT
            )
            # Check if request was successful
            if response.status_code == 200:
                return response.json().get('results', {}).get('bindings', [])

            if attempt == 2 or response.status_code not in SPARQL_RETRY_STATUS:
                logger.error(
                    "SPARQL request to %s failed with status %s: %s",
                    sparql_endpoint,
                    response.status_code,
                    response.text,
                )
                return failed
            retry_after = response.headers.get('Retry-After')
            reason = f"status {response.status_code}"

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt == 2:
                logger.error("SPARQL query to %s failed: %s", sparql_endpoint, e)
                return failed
            reason = type(e).__name__

        except requests.exceptions.RequestException as e:
            logger.exception("SPARQL request failed: %s", e)
            return failed

        except ValueError as e:
            logger.error("SPARQL answer from %s is not valid JSON: %s", sparql_endpoint, e)
            return failed

        wait = SPARQL_RETRY_WAIT
        if retry_after and str(retry_after).isdigit():
            wait = min(float(retry_after), SPARQL_MAX_RETRY_WAIT)
        logger.warning("SPARQL query to %s failed (%s); retrying in %s s.",
                       sparql_endpoint, reason, wait)
        time.sleep(wait)

    return failed

def query_sparql_parts(queries, sparql_endpoint):
    '''Run the parts of a split query one after another and merge their rows.

    The first part decides which items exist and how many rows each has,
    exactly like the full query; every further part returns one row per item
    with its own columns, which are added to that item's rows.

    Args:
        queries:         Part query strings, the deciding part first.
        sparql_endpoint: URL of the SPARQL endpoint.

    Returns:
        List of result-binding dicts shaped like those of the full query; an
        empty list if any part fails, so no item is filled half.
    '''
    results = []
    for number, query in enumerate(queries, 1):
        rows = query_sparql(query, sparql_endpoint, strict=True)
        if rows is None:
            logger.warning(
                "Part %s of %s of a split SPARQL query failed; no items are filled from it.",
                number, len(queries),
            )
            return []
        if not rows and not results:
            return []                 # no item exists, so the other parts have nothing to add
        results.append(rows)

    columns = {}
    for rows in results[1:]:
        for row in rows:
            columns.setdefault(row['id']['value'], {}).update(row)
    return [{**columns.get(row['id']['value'], {}), **row} for row in results[0]]

def query_sparql_pool(query_input):
    '''Execute multiple SPARQL queries in parallel and return a keyed result dict.

    Args:
        query_input: Dict mapping a source key to a ``(query, endpoint)`` tuple,
                     e.g. ``{"mardi": (query_str, url), "wikidata": ...}``;
                     a third element ``True`` makes a failed query give
                     ``None`` (see the *strict* argument of :func:`query_sparql`).

    Returns:
        Dict with the same keys as *query_input*, each mapping to the list of
        SPARQL result bindings returned by :func:`query_sparql`.
    '''
    # Map each endpoint's query and store results in a dictionary; the pool
    # is closed afterwards so its worker threads do not linger
    commit_writes()
    with ThreadPool(processes = len(query_input)) as pool:
        results = pool.map(lambda args: query_sparql(*args), query_input.values())
    data = dict(zip(query_input.keys(), results))
    return data

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


def query_sources(search, item_class=[], sources=None, not_found=True):
    '''Query one or more knowledge-graph sources for items matching *search*.

    Queries the requested sources in parallel (results are cached for five
    minutes, see :func:`_cached_search`), merges the results, and sorts them by
    relevance to *search* using :func:`~.helpers.rank_by_search_term`.

    Args:
        search:     Free-text search string.
        item_class: QID string or list of QID strings used for class-filtered
                    search on MaRDI (e.g. ``"Q42"`` or ``["Q42", "Q43"]``).
                    Wikidata is always searched by label/description only.
        sources:    List of source keys to query; defaults to
                    ``["mardi", "wikidata"]``.
        not_found:  If ``True`` (default), prepends a ``{"id": "not found",
                    "text": "not found"}`` sentinel to the option list.

    Returns:
        List of ``{"id": …, "text": …}`` option dicts, sorted by relevance.
    '''
    if sources is None:
        sources = ['mardi', 'wikidata']

    source_functions = {}
    if 'mardi' in sources:
        source_functions['mardi'] = lambda s: _cached_search(
            'mardi', s, item_class, lambda t: query_api_per_class(t, item_class, raise_errors=True))
    if 'wikidata' in sources:
        source_functions['wikidata'] = lambda s: _cached_search(
            'wikidata', s, None, lambda t: query_api(get_url('wikidata', 'api'), t, raise_errors=True))

    # Runs on every autocomplete search; close the pool so threads do not pile up
    with ThreadPool(processes=len(source_functions)) as pool:
        results = pool.map(lambda func: func(search), source_functions.values())
    results_dict = dict(zip(source_functions.keys(), results))

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
                             f" ({r[display_key].get('description', {}).get('value', 'No Description Provided!')})"
                             f" [wikidata]"),
                }
                for r in raw
                if display_key in r
            ]
        options += raw

    options.sort(key=lambda opt: rank_by_search_term(opt, search))

    if not_found:
        options = [{'id': 'not found', 'text': 'not found'}] + options

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
        )
    except (requests.exceptions.RequestException, KeyError, ValueError, TypeError) as e:
        logger.error("Query sources failed: %s", e)
        options = []

    if setup.get('query_attributes'):
        try:
            dic = query_user_entries(project, setup)
        except Exception as e:
            logger.error("User entries query failed: %s", e)
            dic = {}

        # Filter and merge options
        options_user = [
            {'id': value['id'], 'text': key}
            for key, value in dic.items()
            if search.lower() in key.lower()
        ]
        options = options_user + options

    # Add creation option if needed
    if setup['creation']:
        creation_option = {'id': 'not found', 'text': search}
        if creation_option not in options:
            options.insert(0, creation_option)

    return options

def query_user_entries(project, setup):
    '''Build a label→ID dict from entries the user has already added to the questionnaire.

    Reads the ID, Name, and Description values of all attributes listed in
    ``setup["query_attributes"]`` with two database queries, aligns them by
    ``set_index``/``set_prefix``, and returns only entries whose source is not
    in ``setup["sources"]`` (i.e. not already covered by KG results).

    Args:
        project: RDMO project instance.
        setup:   Configuration dict (see :func:`query_sources_with_user_additions`).

    Returns:
        Dict mapping display strings (``"Label (Description)"`` or
        ``"Label (Description) [source]"``) to ``{"id": item_id}`` dicts.
    '''
    uris = {
        f'{BASE_URI}domain/{query_attribute}/{question}': (query_attribute, question)
        for query_attribute in setup['query_attributes']
        for question in ('id', 'name', 'description')
    }
    attributes = {
        attribute.id: uris[attribute.uri]
        for attribute in Attribute.objects.filter(uri__in=uris)
    }

    # Align id/name/description per entity type and entity index
    entries = {}
    for value in project.values.filter(snapshot=None, attribute_id__in=attributes):
        query_attribute, question = attributes[value.attribute_id]
        idx = value.set_index if question == 'id' else int(value.set_prefix)
        entries.setdefault((setup['query_attributes'].index(query_attribute), idx), {})[question] = value

    dic = {}
    for _, entry in sorted(entries.items()):
        if 'id' not in entry or not entry['id'].text:
            continue
        if entry['id'].text == 'not found':
            # User-defined item
            name, description = entry.get('name'), entry.get('description')
            label = (name.text if name else '') or "No Label Provided!"
            description = (description.text if description else '') or "No Description Provided!"
            item_id = 'not found'
            source = 'user'
        else:
            # External ID item
            label, description, source = extract_parts(entry['id'].text)
            _, item_id = entry['id'].external_id.split(':')
            item_id = f"{source}:{item_id}"
        # Add to dictionary if not from primary sources
        if source not in setup['sources']:
            if source == 'user':
                dic[f"{label} ({description})"] = {'id': item_id}
            else:
                dic[f"{label} ({description}) [{source}]"] = {'id': item_id}
    return dic

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
        List of ``{"id": "mardi:<QID>", "text": "Label (Description) [mardi]"}``
        dicts; empty list on any network error (unless *raise_errors*) or no hits.
    '''
    if isinstance(item_class, str):
        item_class = [item_class]

    instance_of  = get_properties()['instance of']
    class_filter = '|'.join(f'{instance_of}={qid}' for qid in item_class)
    api_url      = get_url('mardi', 'api')

    try:
        search_resp = http_session().get(
            api_url,
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
            timeout=5,
        )
        search_resp.raise_for_status()
        hits = search_resp.json().get('query', {}).get('search', [])
    except requests.exceptions.RequestException as e:
        logger.error("Class-based MaRDI search failed: %s", e)
        if raise_errors:
            raise
        return []

    if not hits:
        return []

    qids = [hit['title'].removeprefix('Item:') for hit in hits]

    try:
        entity_resp = http_session().get(
            api_url,
            params={
                'action':    'wbgetentities',
                'ids':       '|'.join(qids),
                'props':     'labels|descriptions',
                'languages': 'en',
                'format':    'json',
            },
            headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
            timeout=5,
        )
        entity_resp.raise_for_status()
        entities = entity_resp.json().get('entities', {})
    except requests.exceptions.RequestException as e:
        logger.error("MaRDI entity fetch failed: %s", e)
        if raise_errors:
            raise
        return []

    results = []
    for qid in qids:
        entity      = entities.get(qid, {})
        label       = entity.get('labels',       {}).get('en', {}).get('value', qid)
        description = entity.get('descriptions', {}).get('en', {}).get('value',
                                                                        'No Description Provided!')
        results.append({
            'id':   f'mardi:{qid}',
            'text': f'{label} ({description}) [mardi]',
        })

    return results
