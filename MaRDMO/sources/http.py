'''HTTP and SPARQL requests to external services: one session, retries, time limits.

Every request MaRDMO sends to the MaRDI Portal, Wikidata, QLever or the
citation services goes through :func:`http_session` (one session per
thread) and, where a failure is worth a retry, :func:`request_with_retry`.
:func:`query_sparql` runs a SPARQL SELECT query on top of it.  The time
limits of a dropdown search (:func:`search_deadline`) and of the export's
checks (:func:`check_limits`) are set here.
'''
import logging
import random
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from multiprocessing.pool import ThreadPool

import requests

from ..writes import commit_writes

logger = logging.getLogger(__name__)

# A dropdown search request is given up after SEARCH_TIMEOUT seconds and
# retried once after SEARCH_RETRY_WAIT seconds on a quick failure (#94): a
# connection error or one of SPARQL_RETRY_STATUS.  A timeout is not retried
# (search_deadline): the request occupies an RDMO worker all the while
SEARCH_TIMEOUT = 5
SEARCH_RETRY_WAIT = 0.5

# A SPARQL query is given up after this many seconds and retried once on a
# timeout, a connection error or one of these answers, after the portal's
# Retry-After (at most SPARQL_MAX_RETRY_WAIT seconds) or SPARQL_RETRY_WAIT;
# request_with_retry() applies the same rule to other requests
SPARQL_TIMEOUT = 30
SPARQL_RETRY_STATUS = (429, 502, 503, 504)
SPARQL_RETRY_WAIT = 2
SPARQL_MAX_RETRY_WAIT = 10
# A failed export check stops the export, so these requests are retried twice
# (pauses in seconds), and all of a check's requests give up after
# EXPORT_CHECK_DEADLINE seconds
EXPORT_RETRY_WAITS = (2, 5)
EXPORT_CHECK_DEADLINE = 120
# The preview runs the export's checks too (#152), with its own shorter
# limits: check_limits() sets them for the checks in its block
_CHECK_LIMITS = ContextVar('mardmo_check_limits', default=(EXPORT_RETRY_WAITS, EXPORT_CHECK_DEADLINE))


@contextmanager
def check_limits(waits, seconds):
    '''Retry the export's check requests after *waits* and give each check *seconds* in this block.'''
    token = _CHECK_LIMITS.set((waits, seconds))
    try:
        yield
    finally:
        _CHECK_LIMITS.reset(token)


def check_waits():
    '''Pauses before the retries of an export check request (:func:`check_limits`).'''
    return _CHECK_LIMITS.get()[0]


def check_deadline():
    '''The time (``time.monotonic()``) at which an export check starting now gives up.'''
    return time.monotonic() + _CHECK_LIMITS.get()[1]


_SESSIONS = threading.local()


def http_session():
    '''Return this thread's HTTP session for requests to external services.

    Reusing the session keeps connections open, so repeated requests to the
    same service skip the connection setup.  MaRDMO's pending writes are
    committed first (see :func:`~MaRDMO.writes.batched_writes`), so no
    transaction stays open while waiting for the answer.
    '''
    commit_writes()
    session = getattr(_SESSIONS, 'session', None)
    if session is None:
        session = _SESSIONS.session = requests.Session()
    return session


def search_deadline():
    '''Return the deadline of a dropdown search request sent now (:func:`request_with_retry`).

    A failure before :data:`SEARCH_TIMEOUT` seconds leaves time for the
    retry; a timeout does not, so a request never takes much longer than
    without a retry.
    '''
    return time.monotonic() + SEARCH_TIMEOUT + SEARCH_RETRY_WAIT


def request_with_retry(method, url, waits=(SPARQL_RETRY_WAIT,), deadline=None, *, retry_status=SPARQL_RETRY_STATUS,
                       transient=None, jitter=0.0, max_retry_after=SPARQL_MAX_RETRY_WAIT, **kwargs):
    '''Send a request with :func:`http_session` and retry it on transient failures.

    A timeout, a connection error, an answer with one of *retry_status*, or
    an answer *transient* calls a failure is retried after the next pause in
    *waits* (plus up to *jitter* seconds), or later if the answer's
    ``Retry-After`` asks for it (at most *max_retry_after* seconds).  Other
    answers, including 400, are returned at once.  Every caller sets its own
    limits: the export's checks, the dropdowns and the hydration of items
    differ (:mod:`MaRDMO.sources.wikibase`).

    Args:
        method:          HTTP method (``'get'`` or ``'post'``).
        url:             Request URL.
        waits:           Pauses (seconds) before the retries; ``()`` sends the
                         request once.
        deadline:        :func:`time.monotonic` value after which no retry
                         starts; the timeout of each attempt is shortened to
                         end by then.
        retry_status:    The status codes of an answer worth a retry.
        transient:       ``transient(response)``: whether an answer with
                         another status is a failure worth a retry (e.g. a
                         MediaWiki ``error`` in a 200 answer).
        jitter:          Up to this many seconds are added to each pause at random.
        max_retry_after: The longest pause an answer's ``Retry-After`` may ask for.
        **kwargs:        Passed on to :meth:`requests.Session.request`.

    Returns:
        The last :class:`requests.Response`, whatever its status code.

    Raises:
        requests.exceptions.RequestException: If the last attempt failed
            without an answer.
    '''
    timeout = kwargs.pop('timeout', None)
    for wait in (*waits, None):
        if deadline is not None and timeout is not None:
            kwargs['timeout'] = max(1, min(timeout, deadline - time.monotonic()))
        else:
            kwargs['timeout'] = timeout
        error = None
        try:
            response = http_session().request(method, url, **kwargs)
            failed = response.status_code in retry_status or (transient is not None and transient(response))
            if wait is None or not failed:
                return response
            retry_after = response.headers.get('Retry-After')
            if retry_after and str(retry_after).isdigit():
                wait = max(wait, min(float(retry_after), max_retry_after))
            reason = f"status {response.status_code}"
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if wait is None:
                raise
            error, reason = e, type(e).__name__
        if jitter:
            wait += random.uniform(0, jitter)
        if deadline is not None and time.monotonic() + wait >= deadline:
            logger.warning("Request to %s failed (%s); no time left for a retry.", url, reason)
            if error is not None:
                raise error
            return response
        logger.warning("Request to %s failed (%s); retrying in %s s.", url, reason, wait)
        time.sleep(wait)
    return response  # not reached: the last attempt returns or raises


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


def query_sparql(query, sparql_endpoint, strict=False, waits=(SPARQL_RETRY_WAIT,), deadline=None):
    '''Execute a SPARQL SELECT query against *sparql_endpoint* and return bindings.

    Args:
        query:           SPARQL SELECT query string (UTF-8 encoded on the wire).
        sparql_endpoint: URL of the SPARQL endpoint (e.g. the MaRDI or Wikidata endpoint).
        strict:          If ``True``, return ``None`` instead of ``[]`` when the
                         query fails, so callers can tell "failed" from "no results".
        waits:           Pauses before the retries (see :func:`request_with_retry`).
        deadline:        :func:`time.monotonic` value after which no retry starts.

    A query that times out (after :data:`SPARQL_TIMEOUT` seconds), cannot
    connect, or is answered with one of :data:`SPARQL_RETRY_STATUS` is
    retried once (or once per pause in *waits*).

    Returns:
        List of result-binding dicts from ``results.bindings``; on any network
        error, HTTP error, invalid answer, or missing endpoint an empty list
        (or ``None`` with *strict*).
    '''
    failed = None if strict else []

    if not sparql_endpoint:
        logger.warning("SPARQL query attempted without a valid endpoint.")
        return failed

    try:
        response = request_with_retry(
            'post',
            sparql_endpoint,
            waits=waits,
            deadline=deadline,
            data=query.encode("utf-8"),
            headers={
                "User-Agent": "MaRDMO (https://zib.de; reidelbach@zib.de)",
                "Content-Type": "application/sparql-query; charset=UTF-8",
                "Accept": "application/sparql-results+json"
            },
            timeout=SPARQL_TIMEOUT
        )
        # Check if request was successful
        if response.status_code == 200:
            return response.json().get('results', {}).get('bindings', [])
        logger.error(
            "SPARQL request to %s failed with status %s: %s",
            sparql_endpoint,
            response.status_code,
            response.text,
        )

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        logger.error("SPARQL query to %s failed: %s", sparql_endpoint, e)

    except requests.exceptions.RequestException as e:
        logger.exception("SPARQL request failed: %s", e)

    except ValueError as e:
        logger.error("SPARQL answer from %s is not valid JSON: %s", sparql_endpoint, e)

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
