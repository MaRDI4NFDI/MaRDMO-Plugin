'''Utility functions for fetching and normalizing publication metadata.

Provides helpers that query external bibliographic APIs (Crossref, DataCite,
ZbMATH, ORCID), parse their responses, and map the results to the internal
:class:`~MaRDMO.publication.models.Author`, :class:`~MaRDMO.publication.models.Journal`,
and :class:`~MaRDMO.publication.models.Publication` dataclasses.

Provides:

- ``get_citation``            — primary entry point: fetch full citation data for a DOI
- ``get_crossref_data``       — query the Crossref REST API
- ``get_datacite_data``       — query the DataCite REST API
- ``get_doi_data``            — DOI resolver wrapper
- ``get_zbmath_data``         — query the ZbMATH Open API
- ``get_orcids``              — look up ORCID IDs for publication authors
- ``get_author_by_orcid``     — fetch a single author record from the ORCID API
- ``extract_authors``         — parse author list from API response
- ``extract_journals``        — parse journal info from API response
- ``assign_id``               — attach portal / ZbMATH IDs to entity dicts
- ``assign_orcid``            — attach ORCID identifiers to author dicts
- ``clean_background_data``   — remove stale pre-existing answers before filling new ones
- ``additional_queries``      — run supplementary SPARQL queries for linked entities
'''

import hashlib
import logging
import re
from multiprocessing.pool import ThreadPool

import requests

from django.core.cache import cache
from rdmo.projects.models import Value
from rdmo.domain.models import Attribute

from .models import Author, Journal, Publication

from ..constants import BASE_URI
from ..getters import get_items, get_properties, get_sparql_query, get_url
from ..queries import http_session, query_sparql, query_sparql_pool

logger = logging.getLogger(__name__)

# Timeout (seconds) for each external metadata request (Crossref, DataCite,
# zbMATH, DOI resolver, ORCID); the sources are queried in parallel
REQUEST_TIMEOUT = 10

# Citation data of a DOI is reused for this long (preview runs the lookup on
# every click); failed lookups are not kept
CITATION_CACHE_TIMEOUT = 60 * 60

def additional_queries(publication, choice, key, parameter, function):
    '''Run supplemental Wikidata and MaRDI Portal SPARQL queries for a sub-entity type.

    Queries first Wikidata, then MaRDI Portal, using the results of the first
    to refine the second.  Calls *function* to parse raw SPARQL results into
    model instances, then calls :func:`assign_id` to back-fill any missing IDs
    on ``publication[choice].<key>``.

    Args:
        publication: Dict mapping source keys to :class:`~.models.Publication`
                     instances (mutated in place).
        choice:      Active source key (e.g. ``"crossref"``).
        key:         Sub-entity attribute name and query file stem
                     (``"authors"`` or ``"journal"``).
        parameter:   Dict with ``"wikidata"`` and ``"mardi"`` lists of format
                     arguments for the SPARQL query template.
        function:    Callable that parses raw SPARQL results into a ``{index:
                     entity}`` dict (e.g. :func:`extract_authors`).
    '''

    # Get & Extract Information from  Wikidata
    wikidata_query = get_sparql_query(
        f"publication/queries/{key}.sparql"
    ).format(
        *parameter['wikidata']
    )
    wikidata_results = query_sparql(
        wikidata_query,
        get_url('wikidata', 'sparql')
    )
    wikidata_info = function(wikidata_results)

    # Get & Extract Information from MaRDI Portal
    wikidata_id = ' '.join(
        f'"{entity.id}"' if entity.id else '""'
        for entity in wikidata_info.values()
    )

    if wikidata_id:
        parameter['mardi'][-1] = wikidata_id

    mardi_query = get_sparql_query(
        f"publication/queries/{key}.sparql"
    ).format(
        *parameter['mardi']
    )
    mardi_results = query_sparql(
        mardi_query,
        get_url('mardi', 'sparql')
    )
    mardi_info = function(mardi_results)

    # Add (missing) MaRDI Portal / Wikidata IDs to authors
    if mardi_info:
        assign_id(
            getattr(
                publication[choice],
                key
            ),
            mardi_info,
            'mardi'
        )
    elif wikidata_info:
        assign_id(
            getattr(
                publication[choice],
                key
            ),
            wikidata_info,
            'wikidata'
        )

def assign_id(entities, target, prefix):
    '''Back-fill missing or placeholder IDs on *entities* from *target*.

    Matches entities by label (case-insensitive) and overwrites the ``id``,
    ``label``, and ``description`` fields when the entity currently has no ID
    or a placeholder such as ``"not found"``.

    An ID is not given to a second entity: Wikidata often lists an author as
    item and as name string, and the name string then stays a name string.
    Entities with a Wikidata ID are therefore matched first.

    Args:
        entities: Iterable of entity dataclass instances to update.
        target:   Dict of resolved entities (from SPARQL results) to match against.
        prefix:   Source prefix prepended to the resolved ID (e.g. ``"mardi"``).
    '''
    entities = list(entities)
    for entity in sorted(entities, key=lambda e: not (e.id or '').startswith('wikidata')):
        if (
            not entity.id
            or entity.id in ('not found', 'no author found', 'no journal found')
            or entity.id.startswith('wikidata')
        ):
            for id_entity in target.values():
                if any(other.id == f"{prefix}:{id_entity.id}" for other in entities):
                    continue
                if entity.label.lower() == id_entity.label.lower():
                    entity.id = f"{prefix}:{id_entity.id}"
                    entity.label = id_entity.label
                    entity.description = id_entity.description

def assign_orcid(publication, source, id_type = 'orcid'):
    '''Back-fill missing ORCID iDs on authors from the *orcid* lookup result.

    Args:
        publication: Dict mapping source keys to :class:`~.models.Publication`
                     instances (mutated in place).
        source:      Key of the publication entry whose authors are updated.
        id_type:     Key for the ORCID lookup result dict (default ``"orcid"``).
    '''
    for author in publication[source].authors:
        if not author.orcid_id:
            for id_author in publication[id_type].values():
                if author.label == id_author.label:
                    author.orcid_id = id_author.orcid_id

def clean_background_data(key_dict, questions, project, snapshot, set_index):
    '''Delete questionnaire values that were temporarily saved during background processing.

    Args:
        key_dict:  Iterable of question-dict keys to delete.
        questions: Questions dict mapping keys to attribute URI fragments.
        project:   RDMO project instance.
        snapshot:  RDMO snapshot (``None`` for the current working snapshot).
        set_index: Set-index of the entries to delete.
    '''
    for key in key_dict:
        Value.objects.filter(
            attribute_id = Attribute.objects.get(
                uri = f'{BASE_URI}{questions[key]["uri"]}'
            ),
            set_index = set_index,
            project = project,
            snapshot = snapshot
        ).delete()

def extract_authors(data):
    '''Parse SPARQL result rows into a dict of :class:`~.models.Author` instances.

    Expects ``data[0]["author_info"]["value"]`` as a ``" || "``-delimited
    string of author records.

    Args:
        data: Raw SPARQL result list (may be empty).

    Returns:
        Dict ``{index: Author}`` for each non-empty record; empty dict if
        *data* is falsy.
    '''
    authors = {}
    if data:
        for idx, entry in enumerate(data[0].get('author_info', {}).get('value', '').split(" || ")):
            if entry:
                authors[idx] = Author.from_query(entry)
    return authors

def extract_journals(data):
    '''Parse SPARQL result rows into a dict of :class:`~.models.Journal` instances.

    Expects ``data[0]["journal_info"]["value"]`` as a ``" || "``-delimited
    string of journal records.

    Args:
        data: Raw SPARQL result list (may be empty).

    Returns:
        Dict ``{index: Journal}`` for each non-empty record; empty dict if
        *data* is falsy.
    '''
    journals = {}
    if data:
        for idx, entry in enumerate(data[0].get('journal_info', {}).get('value', '').split(" || ")):
            if entry:
                journals[idx] = Journal.from_query(entry)
    return journals

def get_citation(doi):
    '''Retrieve full citation metadata for a DOI from multiple sources.

    Queries MaRDI Portal and Wikidata via SPARQL in parallel.  If neither
    yields a result, falls back to CrossRef, DataCite, zbMath, and the DOI
    metadata service.  Then enriches authors with ORCID iDs and runs
    supplemental author/journal queries against MaRDI Portal and Wikidata.

    The result is cached per DOI for :data:`CITATION_CACHE_TIMEOUT` seconds
    if the MaRDI Portal and Wikidata answered and some source knows the
    publication.  Otherwise the next call looks it up again.

    Args:
        doi: DOI string (e.g. ``"10.1000/xyz123"``).

    Returns:
        Dict mapping source keys (``"mardi"``, ``"wikidata"``, ``"crossref"``,
        etc.) to :class:`~.models.Publication` instances or ``None``; empty
        dict if *doi* does not match the expected format.
    '''
    if not re.match(r'10.\d{4,9}/[-._;()/:a-z0-9A-Z]+', doi):
        return {}

    key = 'mardmo_citation_' + hashlib.sha1(doi.encode('utf-8')).hexdigest()
    publication = cache.get(key)
    if publication is None:
        publication, complete = _lookup_citation(doi)
        if complete:
            cache.set(key, publication, CITATION_CACHE_TIMEOUT)
    return publication


def _lookup_citation(doi):
    '''Look up *doi* in all sources (see :func:`get_citation`).

    Returns:
        Tuple ``(publication, complete)``; *complete* is ``True`` if the MaRDI
        Portal and Wikidata answered and some source knows the publication.
    '''
    publication = {}
    choice = None

    # Define MaRDI Portal / Wikidata / MathAlgoDB SPARQL Queries
    mardi_query = get_sparql_query(
        'publication/queries/full_doi_mardi.sparql'
    ).format(
        doi,
        **get_items(),
        **get_properties()
    )
    wikidata_query = get_sparql_query(
        'publication/queries/full_doi_wikidata.sparql'
    ).format(
        doi
    )

    # Get Citation Data from MaRDI Portal / Wikidata / MathAlgoDB; a failed
    # query gives None (strict), so the result is not cached
    results = query_sparql_pool(
        {
            'wikidata': (wikidata_query, get_url('wikidata', 'sparql'), True),
            'mardi':(mardi_query, get_url('mardi', 'sparql'), True),
        }
    )
    answered = results['mardi'] is not None and results['wikidata'] is not None

    # Structure Publication Information
    for key in ['mardi', 'wikidata']:
        publication[key] = None
        if results.get(key):
            try:
                publication[key] = Publication.from_query(results[key])
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Could not read publication %s from %s", doi, key)

    # Return if Publication found on MaRDI
    if publication['mardi']:
        return publication, answered

    if not publication['wikidata']:
        # If no Citation Data in KGs get information from CrossRef, DataCite, DOI, zbMath
        with ThreadPool(processes=4) as pool:
            results = pool.map(
                lambda fn: fn(doi),
                [
                    get_crossref_data,
                    get_datacite_data,
                    get_zbmath_data,
                    get_doi_data
                ]
            )

        for idx, source in enumerate(['crossref', 'datacite', 'zbmath', 'doi']):
            publication[source] = None
            if hasattr(results[idx], "status_code") and results[idx].status_code == 200:
                # An unexpected answer from one source counts as "not available";
                # the other sources are still used
                try:
                    parsed = getattr(Publication, f"from_{source}")(results[idx])
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.exception("Could not read publication %s from %s", doi, source)
                    continue
                # Without a title the publication cannot be exported; let the
                # next source take over instead of an empty record
                if parsed.label:
                    publication[source] = parsed

    # Get Authors assigned to publication from ORCID
    publication['orcid'] = _orcid_authors(doi)

    # Add (missing) ORCID IDs to authors
    for choice in ['mardi', 'wikidata', 'crossref', 'datacite', 'zbmath', 'doi']:
        if publication.get(choice):
            assign_orcid(publication, choice)
            break
    else:
        choice = None

    # Additional Queries for chosen information source
    if choice:
        # Check if Authors already in MaRDI Portal or Wikidata
        orcid_id = ' '.join(
            f'"{author.orcid_id}"' if author.orcid_id else '""'
            for author in publication[choice].authors
        )
        zbmath_id = ' '.join(
            f'"{author.zbmath_id}"' if author.zbmath_id else '""'
            for author in publication[choice].authors
        )
        wikidata_id = ' '.join(
            f'"{author.wikidata_id}"' if author.wikidata_id else '""'
            for author in publication[choice].authors
        )

        properties = get_properties()
        if orcid_id and zbmath_id and wikidata_id:
            _try_enrichment(
                'authors',
                additional_queries,
                publication,
                choice,
                'authors', 
                {
                    'mardi': [
                        orcid_id,
                        zbmath_id,
                        properties['ORCID iD'],
                        properties['zbMATH author ID'],
                        properties['Wikidata QID'],
                        wikidata_id
                    ],
                    'wikidata': [
                        orcid_id,
                        zbmath_id,
                        'P496',
                        'P1556',
                        '',
                        wikidata_id
                    ],
                },
                extract_authors
            )

        # Check if Journal already in MaRDI Portal or Wikidata
        journal_id = wikidata_id = ""
        if publication[choice].journal:
            if publication[choice].journal[0].issn:
                journal_id = f'"{publication[choice].journal[0].issn}"'
            if (
                publication[choice].journal[0].id
                and 'wikidata' in publication[choice].journal[0].id
            ):
                wikidata_id = f'"{publication[choice].journal[0].id.split(":")[1]}"'

        if journal_id or wikidata_id:
            _try_enrichment(
                'journal',
                additional_queries,
                publication,
                choice,
                'journal',
                {
                    'mardi': [
                        journal_id,
                        properties['ISSN'],
                        properties['Wikidata QID'],
                        wikidata_id
                    ],
                    'wikidata': [
                        journal_id,
                        'P236',
                        '',
                        wikidata_id
                    ],
                },
                extract_journals
            )

    found = any(publication.get(source)
                for source in ('mardi', 'wikidata', 'crossref', 'datacite', 'zbmath', 'doi'))
    return publication, answered and found

def _try_enrichment(label, function, *args):
    '''Run an optional enrichment step (author/journal IDs); log instead of failing.

    The publication data is complete without it, so an unexpected answer from
    the MaRDI Portal or Wikidata must not break the lookup.
    '''
    try:
        function(*args)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Could not look up %s IDs on MaRDI Portal / Wikidata", label)


def _orcid_authors(doi):
    '''Return ``{index: Author}`` for researchers who list *doi* in their ORCID record.

    ORCID only adds missing ORCID iDs to authors from other sources, so any
    failure (service unavailable, unexpected answer) yields ``{}``.
    '''
    authors = {}
    try:
        response = get_orcids(doi)
        if response is None or response.status_code != 200:
            return authors
        for idx, entry in enumerate(response.json().get('result') or []):
            orcid_id = entry.get('orcid-identifier', {}).get('path', '')
            person = get_author_by_orcid(orcid_id)
            if person is not None and person.status_code == 200:
                authors[idx] = Author.from_orcid(person.json())
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Could not look up ORCID authors for %s", doi)
    return authors


def get_crossref_data(doi):
    '''Fetch citation metadata for *doi* from the CrossRef REST API.

    Args:
        doi: DOI string.

    Returns:
        :class:`requests.Response` (status 200) on success, or the caught
        :class:`requests.exceptions.RequestException` on failure.
    '''
    try:
        request = http_session().get(
            f"https://api.crossref.org/works/{doi}",
            timeout = REQUEST_TIMEOUT
        )
        request.raise_for_status()
        return request
    except requests.exceptions.RequestException as error:
        return error

def get_datacite_data(doi):
    '''Fetch citation metadata for *doi* from the DataCite REST API.

    Args:
        doi: DOI string.

    Returns:
        :class:`requests.Response` (status 200) on success, or the caught
        :class:`requests.exceptions.RequestException` on failure.
    '''
    try:
        request = http_session().get(
            f"https://api.datacite.org/dois/{doi}",
            timeout = REQUEST_TIMEOUT
        )
        request.raise_for_status()
        return request
    except requests.exceptions.RequestException as error:
        return error

def get_doi_data(doi):
    '''Fetch citation metadata for *doi* from the DOI metadata service.

    Args:
        doi: DOI string.

    Returns:
        :class:`requests.Response` (status 200) on success, or the caught
        :class:`requests.exceptions.RequestException` on failure.
    '''
    try:
        request = http_session().get(
            f"https://citation.doi.org/metadata?doi={doi}",
            headers = {"accept": "application/json"},
            timeout = REQUEST_TIMEOUT
        )
        request.raise_for_status()
        return request
    except requests.exceptions.RequestException as error:
        return error

def get_zbmath_data(doi):
    '''Fetch citation metadata for *doi* from the zbMath Open API.

    Args:
        doi: DOI string.

    Returns:
        :class:`requests.Response` (status 200) on success, or the caught
        :class:`requests.exceptions.RequestException` on failure.
    '''
    try:
        request = http_session().get(
            f"https://api.zbmath.org/v1/document/_structured_search?page=0&results_per_page=100&DOI={doi}",
            timeout = REQUEST_TIMEOUT
        )
        request.raise_for_status()
        return request
    except requests.exceptions.RequestException as error:
        return error

def get_orcids(doi):
    '''Query the ORCID public API for researchers associated with *doi*.

    Args:
        doi: DOI string used as the ``doi-self`` search criterion.

    Returns:
        :class:`requests.Response` (status 200) containing a JSON payload with
        an ``"result"`` list of ORCID records on success, or ``None``
        on failure (logged as a warning).
    '''
    try:
        request = http_session().get(
            f'https://pub.orcid.org/v3.0/search/?q=doi-self:"{doi}"',
            headers = {'Accept': 'application/json'},
            timeout = REQUEST_TIMEOUT
        )
        request.raise_for_status()
        return request
    except requests.exceptions.RequestException as error:
        logger.warning("ORCID search for %s failed: %s", doi, error)
        return None

def get_author_by_orcid(orcid_id):
    '''Fetch personal-details for a researcher from the ORCID public API.

    Args:
        orcid_id: ORCID iD string (e.g. ``"0000-0002-1825-0097"``).

    Returns:
        :class:`requests.Response` (status 200) containing a JSON payload with
        the researcher's personal details on success, or ``None``
        on failure (logged as a warning).
    '''
    try:
        request = http_session().get(
            f"https://pub.orcid.org/v3.0/{orcid_id}/personal-details",
            headers = {'Accept': 'application/json'},
            timeout = REQUEST_TIMEOUT
        )
        request.raise_for_status()
        return request
    except requests.exceptions.RequestException as error:
        logger.warning("ORCID lookup of %s failed: %s", orcid_id, error)
        return None
