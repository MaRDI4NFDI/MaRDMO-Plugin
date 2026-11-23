'''SPARQL queries of MaRDMO: the query files, and running them (#198).

The queries live as ``.sparql`` files in the packages that use them
(``model/queries/``, ``publication/queries/``, ...); a query too slow for the
portal as one exists only as its parts (``.../split/``), run one after
another (:func:`query_sparql_parts`).  :func:`query_sparql` sends a query
through :func:`~MaRDMO.sources.http.request_with_retry`.
'''
import logging
import os
import re
from functools import lru_cache
from multiprocessing.pool import ThreadPool

import requests

from ..project.writes import commit_writes
from .http import SPARQL_RETRY_WAIT, request_with_retry

logger = logging.getLogger(__name__)

# A SPARQL query is given up after this many seconds (and retried once, see
# SPARQL_RETRY_STATUS in http.py)
SPARQL_TIMEOUT = 30

# The MaRDMO package: the query files' paths are relative to it
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=None)
def get_sparql_query(file_name):
    '''Load and return the contents of a SPARQL query file.

    Result is cached indefinitely after the first read.

    Args:
        file_name: Path relative to the package directory (e.g.
                   ``"model/queries/field.sparql"``).

    Returns:
        Query string (may contain ``{}`` format placeholders).
    '''
    path = os.path.join(PACKAGE_DIR, file_name)
    with open(path, "r", encoding="utf-8") as sparql_file:
        return sparql_file.read()


@lru_cache(maxsize=None)
def get_sparql_query_optional(file_name):
    '''Load a SPARQL query file, returning ``None`` if the file does not exist.

    Result is cached indefinitely after the first read.

    Args:
        file_name: Path relative to the package directory.

    Returns:
        Query string on success; ``None`` when the file is absent.
    '''
    path = os.path.join(PACKAGE_DIR, file_name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as sparql_file:
        return sparql_file.read()


@lru_cache(maxsize=None)
def get_sparql_query_parts(file_name):
    '''Load the split parts of a SPARQL query file, or return ``None`` if it has none.

    The parts of ``model/queries/task_mardi.sparql`` are
    ``model/queries/split/task_mardi_1.sparql``, ``..._2.sparql`` and so on;
    the query itself exists only as these parts.  Each part has only a few
    OPTIONAL blocks, which the portal answers much faster than one query
    with all of them (see ``model/queries/split/README.md``).
    Result is cached indefinitely after the first read.

    Args:
        file_name: Path of the query relative to the package directory.

    Returns:
        Tuple of query strings in part order, or ``None``.
    '''
    folder, name = os.path.split(file_name)
    stem = os.path.splitext(name)[0]
    split_dir = os.path.join(PACKAGE_DIR, folder, 'split')
    if not os.path.isdir(split_dir):
        return None
    pattern = re.compile(rf'{re.escape(stem)}_(\d+)\.sparql')
    numbers = sorted(
        int(match.group(1))
        for match in map(pattern.fullmatch, os.listdir(split_dir))
        if match
    )
    if not numbers:
        return None
    parts = []
    for number in numbers:
        path = os.path.join(split_dir, f'{stem}_{number}.sparql')
        with open(path, "r", encoding="utf-8") as sparql_file:
            parts.append(sparql_file.read())
    return tuple(parts)


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
