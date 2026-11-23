'''HTTP requests to external services: one session, retries, time limits.

Every request MaRDMO sends to the MaRDI Portal, Wikidata, QLever or the
citation services goes through :func:`http_session` (one session per
thread) and, where a failure is worth a retry, :func:`request_with_retry`;
the SPARQL queries (:mod:`MaRDMO.sources.sparql`) too.  The time
limits of a dropdown search (:func:`search_deadline`) and of the export's
checks (:func:`check_limits`) are set here.
'''
import logging
import random
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar

import requests

from ..project.writes import commit_writes

logger = logging.getLogger(__name__)

# A dropdown search request is given up after SEARCH_TIMEOUT seconds and
# retried once after SEARCH_RETRY_WAIT seconds on a quick failure (#94): a
# connection error or one of SPARQL_RETRY_STATUS.  A timeout is not retried
# (search_deadline): the request occupies an RDMO worker all the while
SEARCH_TIMEOUT = 5
SEARCH_RETRY_WAIT = 0.5

# A request is retried once on a timeout, a connection error or one of these
# answers, after the portal's Retry-After (at most SPARQL_MAX_RETRY_WAIT
# seconds) or SPARQL_RETRY_WAIT, unless its caller sets other limits
# (request_with_retry); named after the SPARQL queries, which set the rule
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
    committed first (see :func:`~MaRDMO.project.writes.batched_writes`), so no
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


