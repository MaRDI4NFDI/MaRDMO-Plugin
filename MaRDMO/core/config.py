'''MaRDMO's configuration: vocabularies, questions, URLs (#198).

Fast accessors for what :class:`~MaRDMO.apps.MaRDMOConfig` loads once when
Django starts: the Wikibase vocabulary (items, properties), the RDMO options
and the questions of the catalogs (the answers of a project:
:mod:`MaRDMO.project.answers`), and the URLs of the Wikibase providers.  The
ontology registries (MathModDB, MathAlgoDB) are in
:mod:`MaRDMO.core.properties`, the query files in :mod:`MaRDMO.sources.sparql`.
'''
import json
import os
from functools import lru_cache

from django.apps import apps
from django.conf import settings

from .constants import BASE_URI, WIKIDATA

# The MaRDMO package: the data files' paths are relative to it
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_options():
    '''Return the RDMO options dict from the app config.

    Returns:
        Dict mapping RDMO option URIs to display strings.
    '''
    return apps.get_app_config("MaRDMO").options


def get_items():
    '''Return the Wikibase items dict from the app config.

    Returns:
        Dict mapping item label strings to Wikibase QID strings.
    '''
    return apps.get_app_config("MaRDMO").items


def get_properties():
    '''Return the Wikibase properties dict from the app config.

    Returns:
        Dict mapping property label strings to Wikibase property ID strings.
    '''
    return apps.get_app_config("MaRDMO").properties


def get_questions(question_set):
    '''Return the questions sub-dict for a given catalog question set.

    Args:
        question_set: Key identifying the question set (catalog section name).

    Returns:
        Dict mapping question names to their RDMO attribute URI fragments and
        related metadata.
    '''
    return apps.get_app_config("MaRDMO").questions[question_set]


def catalog_questions(questions, catalog, keep=('Publication',)):
    '''*questions* without the sections and questions *catalog* does not have (#168).

    The model basics catalog shares the questions of the model catalog
    (``questions.json``) but has fewer: no quantities, academic disciplines
    and formula notation.  Answers to these, e.g. written by an older
    MaRDMO, are then not read: they neither block nor reach the portal.
    The sections in *keep* stay complete (a publication's citation data is
    stored without questions).

    Args:
        questions: Questions dict (``get_questions``).
        catalog:   RDMO catalog of the project.
        keep:      Section names to keep as they are.
    '''
    attributes = {f'{element.attribute.uri}' for element in catalog.descendants
                  if getattr(element, 'attribute', None) is not None}
    result = {}
    for name, section in questions.items():
        if name in keep:
            result[name] = section
            continue
        if f'{BASE_URI}{section.get("uri", "")}' not in attributes:
            continue
        result[name] = {key: config for key, config in section.items()
                        if key == 'uri' or not isinstance(config, dict)
                        or f'{BASE_URI}{config.get("uri", "")}' in attributes}
    return result


def get_url(source, url_type):
    '''Return a URL for a Wikibase provider.

    Wikidata URLs are taken from the internal :data:`~MaRDMO.core.constants.WIKIDATA`
    constant.  All other sources are read from ``settings.MARDMO_PROVIDER``.

    Args:
        source:   Provider key — ``"wikidata"`` or a key in ``MARDMO_PROVIDER``.
        url_type: URL type key — one of ``"api"``, ``"sparql"``, or ``"uri"``.

    Returns:
        URL string for the requested source and type.
    '''
    if source == 'wikidata':
        return WIKIDATA[url_type]
    return settings.MARDMO_PROVIDER[source][url_type]


def get_item_url(source):
    '''Return the base URL for browsing Wikibase items on a provider's wiki.

    Wikidata URI is taken from the internal :data:`~MaRDMO.core.constants.WIKIDATA`
    constant.  All other sources are read from ``settings.MARDMO_PROVIDER``.

    Args:
        source: Provider key — ``"wikidata"`` or a key in ``MARDMO_PROVIDER``.

    Returns:
        URL string ending in ``"/wiki/Item:"`` for constructing full item links.
    '''
    if source == 'wikidata':
        return f"{WIKIDATA['uri']}/wiki/Item:"
    return f"{settings.MARDMO_PROVIDER[source]['uri']}/wiki/Item:"


@lru_cache(maxsize=None)
def get_data(file_name):
    '''Load and return JSON data from a file relative to the MaRDMO package root.

    Result is cached indefinitely after the first read.

    Args:
        file_name: Path relative to the package directory (e.g. ``"data/items.json"``).

    Returns:
        Parsed JSON value (typically a dict or list).
    '''
    path = os.path.join(PACKAGE_DIR, file_name)
    with open(path, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    return data


