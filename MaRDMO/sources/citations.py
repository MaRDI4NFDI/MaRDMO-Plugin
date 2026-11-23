'''The citation services: the metadata of a publication by its DOI (#198).

Crossref, DataCite, the DOI resolver (doi.org), zbMATH Open, and ORCID (the
researchers who list the DOI).  Each function returns the service's answer
or the error of the request; combining them into a citation is the
publication's (:func:`MaRDMO.components.publication.utils.get_citation`).
'''
import logging

import requests

from .http import http_session

logger = logging.getLogger(__name__)


# Timeout (seconds) for each external metadata request (Crossref, DataCite,
# zbMATH, DOI resolver, ORCID); the sources are queried in parallel
REQUEST_TIMEOUT = 10


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

    The expanded search returns the names with the ORCID iDs, so no further
    request per researcher is needed.

    Args:
        doi: DOI string used as the ``doi-self`` search criterion.

    Returns:
        :class:`requests.Response` (status 200) containing a JSON payload with
        an ``"expanded-result"`` list of ORCID records on success, or ``None``
        on failure (logged as a warning).
    '''
    try:
        request = http_session().get(
            'https://pub.orcid.org/v3.0/expanded-search/',
            params = {'q': f'doi-self:"{doi}"'},
            headers = {'Accept': 'application/json'},
            timeout = REQUEST_TIMEOUT
        )
        request.raise_for_status()
        return request
    except requests.exceptions.RequestException as error:
        logger.warning("ORCID search for %s failed: %s", doi, error)
        return None
