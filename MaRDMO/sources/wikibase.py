'''The Wikibase API of the MaRDI Portal and Wikidata: entities by their QIDs (#198).

:func:`get_entities` is MaRDMO's one way to ``wbgetentities``.  It asks for
the entities in chunks of :data:`ENTITIES_PER_REQUEST` and retries through
:func:`~MaRDMO.sources.http.request_with_retry`.  How it gives up depends on
its caller:

- **strict** (the default, e.g. the export's checks, the duplicate and DOI
  lookups): the caller's waits and deadline; any chunk that fails raises
  :class:`WikibaseError`, so "the portal did not answer" is never mistaken
  for "the portal has nothing".
- **resilient** (the hydration of items, ``resilient=True``): the waits,
  deadline and limits of :data:`HYDRATION`; a chunk that keeps timing out is
  bisected to isolate one unresponsive entity, and after
  :attr:`Resilience.trip` dead chunks in a row the endpoint's circuit breaker
  opens for :attr:`Resilience.cooldown` seconds.  What resolved is returned;
  a struggling portal degrades to a partial fill-in instead of holding the
  request for minutes.
'''
import logging
import time
from dataclasses import dataclass

import requests

from ..core.config import get_url
from .http import SEARCH_RETRY_WAIT, SEARCH_TIMEOUT, request_with_retry

logger = logging.getLogger(__name__)

USER_AGENT = 'MaRDMO (https://zib.de; reidelbach@zib.de)'

ENTITIES_PER_REQUEST = 50
'''QIDs per ``wbgetentities`` request.'''

STRICT_TIMEOUT = 30
'''Timeout (seconds) of a strict request, unless the caller gives one.'''


@dataclass(frozen=True)
class Resilience:
    '''How the resilient mode of :func:`get_entities` gets through a struggling portal.

    Attributes:
        waits:           Pauses (seconds) before the retries of a chunk.
        jitter:          Up to this many seconds added to each pause.
        max_retry_after: The longest pause the portal's ``Retry-After`` may ask for.
        deadline:        Seconds per call after which nothing is retried or bisected.
        timeout:         Timeout of a request (shortened to the deadline).
        trip:            Dead chunks in a row that open the circuit breaker.
        cooldown:        Seconds the breaker stays open.
    '''
    waits: tuple = (1.0, 2.0, 4.0)
    jitter: float = 0.5
    max_retry_after: float = 20.0
    deadline: float = 45
    timeout: float = 30
    trip: int = 3
    cooldown: float = 120


HYDRATION = Resilience()
'''The limits of the hydration (filling in an item selected in the interview).'''

# The MaRDI Portal answers some failures with status 500, which the
# hydration retries too
_ANY_SERVER_ERROR = tuple(range(500, 600))

# Process-wide circuit-breaker state, keyed by endpoint: while a breaker is
# open, resilient calls to that endpoint return at once with nothing
_breakers: dict = {}


class WikibaseError(requests.exceptions.RequestException):
    '''The Wikibase API did not give the entities: an error status, or a MediaWiki ``error`` answer.'''


class _Outage(Exception):
    '''A chunk that failed with an endpoint-wide error (resilient mode): counts for the breaker.'''


def _api_error(response):
    '''Whether *response* (status 200) is a failure: not JSON, or a MediaWiki ``{"error": …}`` (e.g. a DB error).'''
    try:
        body = response.json()
    except ValueError:
        return True
    return isinstance(body, dict) and 'error' in body


def get_entities(api_url, qids, props, *, languages=None, waits=(), deadline=None, timeout=None, resilient=False):
    '''``{QID: entity}`` of *qids* from the Wikibase API *api_url* (``wbgetentities``).

    Args:
        api_url:   The API endpoint (``…/w/api.php``).
        qids:      The QIDs (``Q1``).
        props:     What of the entities (``'claims'``, ``'labels|descriptions'`` …).
        languages: Only these languages of labels and descriptions (e.g. ``'en'``).
        waits:     Strict mode: pauses before the retries of a chunk.
        deadline:  Strict mode: :func:`time.monotonic` value after which no retry starts.
        timeout:   Strict mode: timeout of a request (default :data:`STRICT_TIMEOUT`).
        resilient: The hydration's mode (:data:`HYDRATION`): partial results
                   instead of an error, bisection, circuit breaker.

    Returns:
        ``{QID: entity}``; in resilient mode possibly partial or empty.

    Raises:
        requests.exceptions.RequestException: Strict mode, if a chunk could
            not be fetched (:class:`WikibaseError` for an error answer).
        ValueError: Strict mode, if an answer is not JSON.
    '''
    params = {'action': 'wbgetentities', 'props': props, 'format': 'json'}
    if languages:
        params['languages'] = languages
    qids = list(qids)
    if resilient:
        return _resilient(api_url, params, qids)
    entities = {}
    for start in range(0, len(qids), ENTITIES_PER_REQUEST):
        response = request_with_retry(
            'get', api_url, waits=waits, deadline=deadline,
            timeout=STRICT_TIMEOUT if timeout is None else timeout,
            headers={'User-Agent': USER_AGENT},
            params={**params, 'ids': '|'.join(qids[start:start + ENTITIES_PER_REQUEST])},
        )
        if response.status_code >= 400:
            raise WikibaseError(f'wbgetentities: HTTP {response.status_code}', response=response)
        body = response.json()
        if isinstance(body, dict) and 'error' in body:
            raise WikibaseError(f"wbgetentities: {body['error'].get('code', 'error')}", response=response)
        entities.update(body.get('entities', {}))
    return entities


def _resilient(api_url, params, qids):
    '''The resilient mode of :func:`get_entities`.'''
    if _breaker_open(api_url):
        logger.warning("wbgetentities: circuit open for %s, skipping %s qids", api_url, len(qids))
        return {}
    entities = {}
    deadline = time.monotonic() + HYDRATION.deadline
    for start in range(0, len(qids), ENTITIES_PER_REQUEST):
        try:
            entities.update(_chunk(api_url, params, qids[start:start + ENTITIES_PER_REQUEST], deadline))
        except _Outage:
            _record_failure(api_url)
            if _breaker_open(api_url):
                logger.error("wbgetentities: %s unresponsive, aborting batch", api_url)
                break
        else:
            _reset(api_url)
    return entities


def _chunk(api_url, params, chunk, deadline):
    '''``{QID: entity}`` of one chunk (resilient mode); a chunk that keeps timing out is bisected.

    Raises:
        _Outage: The chunk still fails after the retries with an endpoint-wide
            error (status, connection, MediaWiki error, no JSON).
    '''
    try:
        response = request_with_retry(
            'get', api_url, waits=HYDRATION.waits, deadline=deadline, timeout=HYDRATION.timeout,
            retry_status=_ANY_SERVER_ERROR, transient=_api_error, jitter=HYDRATION.jitter,
            max_retry_after=HYDRATION.max_retry_after,
            headers={'User-Agent': USER_AGENT}, params={**params, 'ids': '|'.join(chunk)},
        )
    except requests.exceptions.Timeout:
        # A persistent timeout may be one oversized entity: bisect to isolate it
        if len(chunk) > 1 and time.monotonic() < deadline:
            middle = len(chunk) // 2
            return {**_chunk(api_url, params, chunk[:middle], deadline),
                    **_chunk(api_url, params, chunk[middle:], deadline)}
        logger.error("wbgetentities failed for %s..%s", chunk[0], chunk[-1])
        return {}
    except requests.exceptions.RequestException as error:
        logger.error("wbgetentities failed for %s..%s", chunk[0], chunk[-1])
        raise _Outage(str(error)) from error
    if response.status_code >= 400 or _api_error(response):
        logger.error("wbgetentities failed for %s..%s", chunk[0], chunk[-1])
        raise _Outage(f'HTTP {response.status_code}')
    return response.json().get('entities', {})


def _breaker_open(api_url):
    '''True while *api_url*'s breaker is within its cooldown window.'''
    return time.monotonic() < _breakers.get(api_url, {}).get('open_until', 0)


def _record_failure(api_url):
    '''Count one dead chunk; open the breaker once the streak reaches :attr:`Resilience.trip`.'''
    breaker = _breakers.setdefault(api_url, {'fails': 0, 'open_until': 0})
    breaker['fails'] += 1
    if breaker['fails'] >= HYDRATION.trip:
        breaker['open_until'] = time.monotonic() + HYDRATION.cooldown


def _reset(api_url):
    '''Clear the failure streak of *api_url* after a chunk that resolved.'''
    if api_url in _breakers:
        _breakers[api_url] = {'fails': 0, 'open_until': 0}


# Hits of a Wikidata label search: 10 shown unfiltered; 50 asked for where
# they are filtered by their classes, which leaves out most of them (#170)
WIKIDATA_HITS = 10


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


# The lookups of publication twins while a page is filled (#158): requests are
# given up after this many seconds and retried once; wbgetentities takes at
# most 50 items, a search for DOIS_PER_SEARCH DOIs finds at most 50 items
TWIN_TIMEOUT = 10


def entities_of(source, qids, props, waits=(SEARCH_RETRY_WAIT,), deadline=None):
    '''``{QID: entity}`` of *qids* on *source* (``wbgetentities``, English labels); raises on request errors.

    An error answer of the portal raises too (:class:`~MaRDMO.sources.wikibase.WikibaseError`):
    it is "the portal did not answer", not "the portal has nothing".
    '''
    return get_entities(get_url(source, 'api'), qids, props, languages='en', waits=waits, deadline=deadline,
                        timeout=TWIN_TIMEOUT)


def claim_values(entity, prop):
    '''The string values of the statements *prop* of *entity* (from ``wbgetentities``).'''
    return [claim['mainsnak']['datavalue']['value'] for claim in entity.get('claims', {}).get(prop, [])
            if claim.get('mainsnak', {}).get('snaktype') == 'value'
            and isinstance(claim['mainsnak']['datavalue']['value'], str)]


def entity_classes(entity, instance_of):
    '''The QIDs of the classes (*instance_of* statements) of a ``wbgetentities`` *entity*.'''
    return {claim['mainsnak'].get('datavalue', {}).get('value', {}).get('id')
            for claim in entity.get('claims', {}).get(instance_of, [])}


def search_by_statement(api_url, statement, namespace, limit=10, waits=(), deadline=None, timeout=None):
    '''The QIDs of the items with *statement* (``P27=10.…``), by the search of the Wikibase API *api_url*.

    ``haswbstatement`` ignores the case of a DOI.  *namespace* is the
    namespace of the items (120 on the MaRDI Portal, 0 on Wikidata).

    Raises:
        requests.exceptions.RequestException: If the search fails.
    '''
    found = request_with_retry(
        'get', api_url, waits=waits, deadline=deadline, headers={'User-Agent': USER_AGENT},
        timeout=STRICT_TIMEOUT if timeout is None else timeout,
        params={'action': 'query', 'list': 'search', 'srsearch': f'haswbstatement:{statement}',
                'srnamespace': namespace, 'srlimit': limit, 'format': 'json'},
    )
    found.raise_for_status()
    return [hit['title'].rsplit(':', 1)[-1] for hit in found.json().get('query', {}).get('search', [])]
