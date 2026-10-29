'''Functions to retrieve configuration data and questionnaire values for MaRDMO.

Provides fast, app-config-backed accessors for Wikibase vocabulary (items,
properties), ontology registries (MathModDB, MathAlgoDB), RDMO question
definitions, and project answer values.  Most getters are thin wrappers
around :attr:`~MaRDMO.apps.MaRDMOConfig` attributes or
:func:`~functools.lru_cache`-decorated file readers.

Provides:

- ``get_mathmoddb``              — return a :class:`~.helpers.PropertyRegistry` for MathModDB
- ``get_mathalgodb``             — return a :class:`~.helpers.PropertyRegistry` for MathAlgoDB
- ``get_publication_mapping``    — return a :class:`~.helpers.PropertyRegistry` for shared publication roles
- ``get_options``                — return the RDMO options dict from the app config
- ``get_items``                  — return the Wikibase items dict from the app config
- ``get_properties``             — return the Wikibase properties dict from the app config
- ``get_questions``              — return the questions sub-dict for a given catalog section
- ``get_url``                    — return a configured URL for a Wikibase provider
- ``get_item_url``               — return the base item-browse URL for a Wikibase provider
- ``get_data``                   — load and cache JSON data from a package-relative file
- ``get_sparql_query``           — load and cache a SPARQL query file
- ``get_sparql_query_optional``  — load and cache a SPARQL query file, or ``None`` if absent
- ``get_id``                     — retrieve attribute field(s) from all questionnaire values at a URI
- ``get_answers``                — read questionnaire values for one attribute and merge into a dict
'''

import json
import os
from functools import lru_cache

from django.apps import apps
from django.conf import settings
from rdmo.domain.models import Attribute

from .constants import BASE_URI, WIKIDATA
from .constants import flag_dict
from .helpers import PropertyRegistry, nested_set
def get_mathmoddb():
    '''Return a :class:`~.helpers.PropertyRegistry` for the MathModDB ontology.

    Returns:
        :class:`~.helpers.PropertyRegistry` wrapping
        :attr:`~MaRDMO.apps.MaRDMOConfig.mathmoddb`.
    '''
    return PropertyRegistry(
        apps.get_app_config("MaRDMO").mathmoddb
    )

def get_mathalgodb():
    '''Return a :class:`~.helpers.PropertyRegistry` for the MathAlgoDB ontology.

    Returns:
        :class:`~.helpers.PropertyRegistry` wrapping
        :attr:`~MaRDMO.apps.MaRDMOConfig.mathalgodb`.
    '''
    return PropertyRegistry(
        apps.get_app_config("MaRDMO").mathalgodb
    )

def get_publication_mapping():
    '''Return a :class:`~.helpers.PropertyRegistry` for the shared publication role options.

    Returns:
        :class:`~.helpers.PropertyRegistry` wrapping
        :attr:`~MaRDMO.apps.MaRDMOConfig.publication_mapping`.
    '''
    return PropertyRegistry(
        apps.get_app_config("MaRDMO").publication_mapping
    )

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

def get_url(source, url_type):
    '''Return a URL for a Wikibase provider.

    Wikidata URLs are taken from the internal :data:`~MaRDMO.constants.WIKIDATA`
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

    Wikidata URI is taken from the internal :data:`~MaRDMO.constants.WIKIDATA`
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
    path = os.path.join(os.path.dirname(__file__), file_name)
    with open(path, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    return data

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
    path = os.path.join(os.path.dirname(__file__), file_name)
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
    path = os.path.join(os.path.dirname(__file__), file_name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as sparql_file:
        return sparql_file.read()

def get_id(project, uri, keys):
    '''Retrieve one or more attribute fields from all questionnaire values at *uri*.

    Args:
        project: RDMO project instance.
        uri:     Full RDMO attribute URI to filter on.
        keys:    List of :class:`~rdmo.projects.models.Value` field names to
                 read (e.g. ``["set_index"]``, ``["external_id"]``, or
                 ``["set_index", "set_prefix"]``).  When *keys* has exactly
                 one element, multi-value pipe-separated strings are split and
                 only the first part is returned.

    Returns:
        List of scalar values (single-key case) or list of lists (multi-key
        case), one entry per matching questionnaire value.
    '''
    values = project.values.filter(
        snapshot=None,
        attribute=Attribute.objects.get(
            uri=uri
        )
    )
    identifiers = []
    if len(keys) == 1:
        for value in values:
            identifier = getattr(value, keys[0])
            if isinstance(identifier, str) and '|' in identifier:
                identifier = identifier.split('|')[0]
            identifiers.append(identifier)
    else:
        for value in values:
            identifier = []
            for key in keys:
                identifier.append(getattr(value, key))
            identifiers.append(identifier)
    return identifiers

def get_answers(project, val, config):
    '''Read questionnaire values for one attribute and merge them into *val*.

    Iterates over all :class:`~rdmo.projects.models.Value` objects for the
    attribute described by *config*, determines the appropriate path in *val*
    via a :data:`~.constants.flag_dict` handler, and calls
    :func:`~.helpers.nested_set` to write the entry.

    Args:
        project: RDMO project instance.
        val:     Top-level answers dict that is mutated in place.
        config:  Dict describing how to map a questionnaire attribute to *val*:

                 * ``"uri"``              – RDMO attribute URI fragment
                 * ``"key1"``             – top-level key in *val*
                 * ``"key2"``             – second-level key (may be empty)
                 * ``"set_prefix"``       – bool flag: use set_prefix as path element
                 * ``"set_index"``        – bool flag: use set_index as path element
                 * ``"collection_index"`` – bool flag: use collection_index
                 * ``"external_id"``      – bool flag: write external_id field
                 * ``"option_text"``      – bool flag: write option URI as text

    Returns:
        The mutated *val* dict.
    '''

    val.setdefault(config["key1"], {})

    try:
        values = project.values.filter(
            snapshot=None,
            attribute=Attribute.objects.get(uri = f"{BASE_URI}{config['uri']}")
            )
    except Attribute.DoesNotExist:
        values = []

    if not (config["key1"] or config["key2"]):
        return val

    for value in values:

        # Set Prefix IDX
        prefix_idx = None
        if value.set_prefix:
            prefix_idx = int(value.set_prefix.split('|')[0])

        # Set Flags
        flags = (
                 bool(config["set_prefix"]),
                 bool(config["set_index"]),
                 bool(config["collection_index"]),
                 bool(config["external_id"]),
                 bool(config["option_text"]),
                )

        # Set Attribute
        attribute = 'option_uri' if value.option else 'text' if value.text else None

        if not attribute:
            # Ignore if not Attribute Set
            continue

        # Get Flag Combo Handler
        handler = flag_dict[flags]

        # Get Entry and Path
        entry, path = handler(value, attribute, config, prefix_idx)

        # Generate nested Dict Entry
        nested_set(data=val,
                   path=path,
                   entry=entry)

    return val
