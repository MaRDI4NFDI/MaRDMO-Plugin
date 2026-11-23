'''Functions that query external data sources (Wikibase API, SPARQL endpoints, Crossref, etc.).

Provides helpers for:

* ``query_api`` – Wikibase ``wbsearchentities`` lookups
* ``find_portal_items`` – duplicates, Wikidata twins and markers on the MaRDI Portal (#141)
* ``query_sources`` / ``query_sources_with_user_additions`` – combined
  MaRDI + Wikidata search with optional user-defined entries
* ``query_api_per_class`` – class-filtered full-text search on the MaRDI portal
* ``query_api_per_profile`` – search of the MaRDI portal by MaRDI profile (faceted search)
* ``option_help`` – the layout of a dropdown option (badge, label, description)

The requests themselves (session, retries, time limits, SPARQL):
:mod:`MaRDMO.sources.http`.
'''
import hashlib
import html
import json
import logging
import re
from itertools import zip_longest
from multiprocessing.pool import ThreadPool

import requests
from django.core.cache import cache
from rdmo.domain.models import Attribute

from .constants import BASE_URI
from .getters import get_mathmoddb, get_properties, get_url
from .sources.portal import portal_doi_forms, query_api_per_class, query_api_per_profile
from .sources.wikibase import WIKIDATA_HITS, entities_of, entity_classes, get_entities, query_api
from .sources.wikidata import WIKIDATA_DOI, wikidata_matches
from .sources.http import (
    SEARCH_RETRY_WAIT,
    SEARCH_TIMEOUT,
    request_with_retry,
    search_deadline,
)
from .values import extract_parts
from .ids import (
    DOI_PREFIX, NEW_DOI, NEW_ITEM, NOT_FOUND, is_item_id, is_user_id, item_text, publication_doi,
)
from .validators import doi_problem

logger = logging.getLogger(__name__)

# Search results of the MaRDI Portal and Wikidata are reused for this long
SEARCH_CACHE_TIMEOUT = 5 * 60
WIKIDATA_FILTERED_HITS = 50


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


def _items_with_statement(source, statement):
    '''Options ``{id, text}`` of the items of *source* (``mardi``, ``wikidata``) with *statement* (``P27=10.…``).

    A search for the statement (``haswbstatement``, which ignores the case of
    a DOI), then the items' English labels and descriptions.  Raises on
    request errors (:func:`_cached_search` does not keep a failed search).
    '''
    api_url = get_url(source, 'api')
    headers = {'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'}
    found = request_with_retry(
        'get', api_url, waits=(SEARCH_RETRY_WAIT,), deadline=search_deadline(), headers=headers,
        timeout=SEARCH_TIMEOUT,
        params={'action': 'query', 'list': 'search', 'srsearch': f'haswbstatement:{statement}',
                'srnamespace': 120 if source == 'mardi' else 0, 'srlimit': 10, 'format': 'json'},
    )
    found.raise_for_status()
    qids = [hit['title'].rsplit(':', 1)[-1] for hit in found.json().get('query', {}).get('search', [])]
    if not qids:
        return []
    entities = get_entities(api_url, qids, 'labels|descriptions', languages='en', waits=(SEARCH_RETRY_WAIT,),
                            deadline=search_deadline(), timeout=SEARCH_TIMEOUT)
    return [{'id': f'{source}:{qid}',
             'text': item_text(entities.get(qid, {}).get('labels', {}).get('en', {}).get('value', qid),
                               entities.get(qid, {}).get('descriptions', {}).get('en', {}).get(
                                   'value', 'No Description Provided!'))}
            for qid in qids]


def find_publications(doi):
    '''The publications with the DOI *doi*: ``(on the MaRDI Portal, on Wikidata)``, each a list of options.

    Both are searched at once; results are reused for five minutes
    (:func:`_cached_search`).  A source that does not answer finds nothing.
    '''
    statements = {'mardi': '|'.join(f"{get_properties()['DOI']}={form}" for form in portal_doi_forms(doi)),
                  'wikidata': f'{WIKIDATA_DOI}={doi.upper()}'}
    with ThreadPool(processes=2) as pool:
        mardi, wikidata = pool.map(
            lambda source: _cached_search(source, f'{DOI_PREFIX}{doi}', 'DOI',
                                          lambda _: _items_with_statement(source, statements[source])),
            ['mardi', 'wikidata'])
    return mardi, wikidata


def publication_options(search):
    '''The options of the publication dropdown for *search*, the identifier with its prefix (#158).

    Only an identifier is searched for (``doi:10.1000/x``), no title.  A
    publication on the MaRDI Portal is offered as the portal item only (the
    Wikidata item would be a duplicate), one only on Wikidata as the
    Wikidata item; one found nowhere as a new publication: the option is
    the identifier itself (ID ``new:doi:…``, tagged "new").  An identifier
    that is not valid is offered too, without asking anyone: saving it is
    refused with the reason (the pre-save validator), which the user would
    not learn from an empty dropdown.
    '''
    doi = publication_doi(search)
    if not doi:
        return []
    new = [{'id': f'{NEW_DOI}{doi}', 'text': f'{DOI_PREFIX}{doi}', 'help': option_help(NEW_DOI, f'{DOI_PREFIX}{doi}')}]
    if doi_problem(doi):
        return new
    mardi, wikidata = find_publications(doi)
    found = mardi or wikidata
    return [{**option, 'help': option_help(option['id'], option['text'])} for option in found] if found else new


def _label_description(option):
    '''Return ``(label, description)`` of an option, to offer a Wikidata hit only once.

    The label is compared case-insensitively, the description exactly.
    Options without a description give ``None``: a matching label alone
    does not make two items the same.
    '''
    label, description, _ = extract_parts(option['text'])
    if not description or description == 'No Description Provided!':
        return None
    return label.strip().lower(), description.strip()


def wikidata_hits(hits, roots, noise=None):
    '''The Wikidata search *hits* that are at or below *roots*, in their order (#170).

    With *noise* instead of *roots*, those that are not an instance of one of
    its classes.  Without either, or if the check of their classes fails,
    the first :data:`WIKIDATA_HITS` hits, unfiltered, as before the check.
    '''
    if roots is None and noise is None:
        return hits[:WIKIDATA_HITS]
    matches = wikidata_matches([hit['id'] for hit in hits if 'id' in hit], roots=roots,
                               noise=None if roots is not None else noise)
    if matches is None:
        return hits[:WIKIDATA_HITS]
    return [hit for hit in hits if matches.get(hit.get('id'))]


def query_sources(search, item_class=None, sources=None, not_found=True, roots=None, noise=None, profiles=None,
                  exclude=None):
    '''Query one or more knowledge-graph sources for items matching *search*.

    Queries the requested sources in parallel (results are cached for five
    minutes, see :func:`_cached_search`), merges the results, and sorts them by
    relevance to *search* using :func:`~.queries.rank_by_search_term`.
    A Wikidata result with the same label and description as a MaRDI result
    is left out: it is the same item, and the export would ask the user to
    select the MaRDI one.

    Args:
        search:     Free-text search string.
        item_class: QID string or list of QID strings used for class-filtered
                    search on MaRDI (e.g. ``"Q42"`` or ``["Q42", "Q43"]``);
                    the classes without a MaRDI profile, where *profiles* is given.
        sources:    List of source keys to query; defaults to
                    ``["mardi", "wikidata"]``.
        not_found:  If ``True`` (default), prepends the option ``{"id": "not found",
                    "text": "new item"}`` to the option list.
        roots:      Wikidata classes the Wikidata hits must be at or below
                    (:func:`wikidata_hits`); ``None``: Wikidata is searched by
                    label only, as before.
        noise:      Instead of *roots* (where no class fits): Wikidata classes
                    the Wikidata hits must not be instances of.
        profiles:   QIDs of MaRDI profiles whose items are searched on the
                    portal (:func:`query_api_per_profile`), in parallel with
                    the class search of *item_class* if there is one.
        exclude:    QIDs of classes whose items the profile search leaves out.

    Returns:
        List of ``{"id": …, "text": "Label (Description)", "help": source tag}``
        option dicts, sorted by relevance; "new item" has no help.
    '''
    if sources is None:
        sources = ['mardi', 'wikidata']

    source_functions = {}
    if 'mardi' in sources:
        if item_class or not profiles:
            source_functions['mardi'] = lambda s: _cached_search(
                'mardi', s, item_class, lambda t: query_api_per_class(t, item_class, raise_errors=True))
        if profiles:
            # The items with a profile (most have no class), in parallel (#170);
            # the cached results depend on the classes left out, too
            scope = list(profiles) + [f'not:{qid}' for qid in exclude or []]
            source_functions['mardi-profiles'] = lambda s: _cached_search(
                'mardi-profiles', s, scope, lambda t: query_api_per_profile(t, profiles, exclude, raise_errors=True))
    if 'wikidata' in sources:
        # One search for all dropdowns (its first hits are those of a shorter
        # one); each filters them by its classes, in parallel with the portal
        source_functions['wikidata'] = lambda s: wikidata_hits(_cached_search(
            'wikidata', s, None, lambda t: query_api(get_url('wikidata', 'api'), t, raise_errors=True,
                                                     waits=(SEARCH_RETRY_WAIT,), deadline=search_deadline(),
                                                     limit=WIKIDATA_FILTERED_HITS)), roots, noise)

    # Runs on every autocomplete search; close the pool so threads do not pile up
    with ThreadPool(processes=len(source_functions)) as pool:
        results = pool.map(lambda func: func(search), source_functions.values())
    results_dict = dict(zip(source_functions.keys(), results))
    if 'mardi-profiles' in results_dict:
        # Taken in turns, so that the first 25 have hits of both searches
        merged = {}
        for pair in zip_longest(results_dict.get('mardi', []), results_dict.pop('mardi-profiles')):
            merged.update({option['id']: option for option in pair if option and option['id'] not in merged})
        results_dict['mardi'] = list(merged.values())

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
                             f" ({r[display_key].get('description', {}).get('value', 'No Description Provided!')})"),
                }
                for r in raw
                if display_key in r
            ]
        options += raw

    # A Wikidata item with the label and description of a MaRDI item is that
    # item; offer only the MaRDI one, the export would ask to select it anyway
    mardi_items = {_label_description(opt) for opt in options if opt['id'].startswith('mardi:')}
    mardi_items.discard(None)
    options = [opt for opt in options
               if not (opt['id'].startswith('wikidata:') and _label_description(opt) in mardi_items)]

    options.sort(key=lambda opt: rank_by_search_term(opt, search))
    # The source is shown grey in the open dropdown, not stored (#103)
    options = [{**option, 'help': option_help(option['id'], option['text'])} for option in options]

    if not_found:
        options = [{'id': NOT_FOUND, 'text': NEW_ITEM}] + options

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
                 * ``answer_class``     – MathModDB class key (``Quantity`` or
                   ``QuantityKind``) the user's own quantities must have;
                   quantities without a class yet are offered too
                 * ``roots``            – Wikidata classes the Wikidata hits
                   must be at or below (``None``: not filtered)
                 * ``noise``            – instead of roots: Wikidata classes
                   the Wikidata hits must not be instances of
                 * ``profiles``, ``exclude`` – MaRDI profiles whose items the
                   portal search finds too, classes whose items it leaves out

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
            roots=setup.get('roots'),
            noise=setup.get('noise'),
            profiles=setup.get('profiles'),
            exclude=setup.get('exclude'),
        )
    except (requests.exceptions.RequestException, KeyError, ValueError, TypeError) as e:
        logger.error("Query sources failed: %s", e)
        options = []

    if setup.get('query_attributes'):
        try:
            options_user = query_user_entries(project, setup)
        except Exception as e:
            logger.error("User entries query failed: %s", e)
            options_user = []

        # Filter and merge options
        options = [option for option in options_user if search.lower() in option['text'].lower()] + options

    # Add creation option if needed
    if setup['creation']:
        if not any(option['id'] == NOT_FOUND and option['text'] == search for option in options):
            options.insert(0, {'id': NOT_FOUND, 'text': search, 'help': option_help(NOT_FOUND, search)})

    return options

def query_user_entries(project, setup):
    '''Return the options of the items the user has already added to the questionnaire.

    Reads the ID, Name, and Description values of all attributes listed in
    ``setup["query_attributes"]`` with two database queries, aligns them by
    ``set_index``/``set_prefix``, and returns only entries whose source is not
    in ``setup["sources"]`` (i.e. not already covered by KG results).  With
    ``setup["answer_class"]``, quantities of the other class are left out.

    Args:
        project: RDMO project instance.
        setup:   Configuration dict (see :func:`query_sources_with_user_additions`).

    Returns:
        List of ``{"id": …, "text": "Label (Description)", "help": source tag}``
        options (:func:`option_help`).
    '''
    uris = {
        f'{BASE_URI}domain/{query_attribute}/{question}': (query_attribute, question)
        for query_attribute in setup['query_attributes']
        for question in ('id', 'name', 'description')
    }
    wanted_class = None
    if setup.get('answer_class'):
        uris[f'{BASE_URI}domain/quantity/is-quantity-or-quantity-kind'] = ('quantity', 'class')
        wanted_class = get_mathmoddb().get(key=setup['answer_class'])['url']
    attributes = {
        attribute.id: uris[attribute.uri]
        for attribute in Attribute.objects.filter(uri__in=uris)
    }

    # Align id/name/description per entity type and entity index
    entries = {}
    for value in project.values.filter(snapshot=None, attribute_id__in=attributes).select_related('option'):
        query_attribute, question = attributes[value.attribute_id]
        idx = value.set_index if question in ('id', 'class') else int(value.set_prefix)
        entries.setdefault((setup['query_attributes'].index(query_attribute), idx), {})[question] = value

    options = []
    for _, entry in sorted(entries.items()):
        if 'id' not in entry or not entry['id'].text:
            continue
        # Quantity of the other class; without a class yet it is offered
        if entry.get('class') and entry['class'].option and entry['class'].option.uri != wanted_class:
            continue
        if not is_item_id(entry['id'].external_id):
            # No real ID (made before MaRDMO 0.8.0): reported by the checks
            continue
        # Offered with the ID, name and description of its page (as preview
        # and export show it); a portal page not filled yet by its ID's text
        name, description = entry.get('name'), entry.get('description')
        name, description = (name.text if name else ''), (description.text if description else '')
        if not name and not is_user_id(entry['id'].external_id):
            name, description, _ = extract_parts(entry['id'].text)
        label = name or "No Label Provided!"
        description = description or "No Description Provided!"
        item_id = entry['id'].external_id
        # Only the sources the dropdown does not search
        if item_id.split(':', 1)[0] not in setup['sources']:
            options.append({'id': item_id, 'text': item_text(label, description),
                            'help': option_help(item_id, item_text(label, description))})
    return options


# A search text that names an item, ``mardi:Q123`` or ``wikidata:Q42``; the
# prefix in any case, spaces around the colon allowed (#170)
TYPED_ITEM_ID = re.compile(r'\s*(mardi|wikidata)\s*:\s*(q[1-9][0-9]*)\s*', re.IGNORECASE)


def typed_item_id(search):
    '''``(source, QID)`` if *search* names an item (:data:`TYPED_ITEM_ID`), else ``None``.'''
    match = TYPED_ITEM_ID.fullmatch(search or '')
    return (match[1].lower(), match[2].upper()) if match else None


def item_by_id(source, qid, classes=None, profiles=None, exclude=None, roots=None, noise=None):
    '''The option of the item *qid* of *source* named in a dropdown, if it fits it; ``[]`` otherwise (#170).

    The item fits as a search hit would: on the portal if it is of one of
    *classes* or has one of *profiles* and is not of a class of *exclude*; on
    Wikidata if it is at or below *roots* or not of a class of *noise*
    (:mod:`~MaRDMO.sources.wikidata`; if the check fails, as unfiltered hits do).
    A merged item is offered as the item it was merged into; an item that
    does not exist is not offered.

    Args:
        source:   ``'mardi'`` or ``'wikidata'``.
        qid:      The item's QID.
        classes:  QIDs of the dropdown's portal classes (all of them).
        profiles: QIDs of the MaRDI profiles of its classes.
        exclude:  QIDs of classes whose items it leaves out.
        roots:    Wikidata classes its Wikidata hits must be at or below.
        noise:    Instead of *roots*: Wikidata classes they must not be instances of.

    Returns:
        ``[option]`` or ``[]``.
    '''
    try:
        entities = entities_of(source, [qid], 'labels|descriptions|claims' if source == 'mardi'
                             else 'labels|descriptions', deadline=search_deadline())
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Lookup of %s:%s failed: %s", source, qid, e)
        return []
    entity = entities.get(qid) or next(iter(entities.values()), {})
    if not entity or 'missing' in entity:
        return []
    # wbgetentities answers a merged item with the one it was merged into
    target = entity.get('id', qid)

    if source == 'mardi':
        properties = get_properties()
        found = entity_classes(entity, properties['instance of'])
        if not (found & set(classes or []) or entity_classes(entity, properties['MaRDI profile type']) & set(profiles or [])):
            return []
        if found & set(exclude or []):
            return []
    elif roots is not None or noise is not None:
        matches = wikidata_matches([target], roots=roots, noise=None if roots is not None else noise)
        if matches is not None and not matches.get(target):
            return []

    label = entity.get('labels', {}).get('en', {}).get('value', target)
    description = entity.get('descriptions', {}).get('en', {}).get('value', 'No Description Provided!')
    item_id, text = f'{source}:{target}', item_text(label, description)
    return [{'id': item_id, 'text': text, 'help': option_help(item_id, text)}]


def rank_by_search_term(option, term):
    '''Return a numeric sort key indicating how well *option* matches *term*.

    Lower values sort first (better match):

    * 0 – label is exact match
    * 1 – label starts with term
    * 2 – label contains term
    * 3 – description contains term
    * 4 – no match

    Args:
        option: Option dict with a ``text`` field in
                ``"Label (Description)"`` format.
        term:   Search string entered by the user.

    Returns:
        Integer rank value 0–4.
    '''
    label, desc, _ = extract_parts(option['text'])
    label_lower = label.lower()
    term_lower  = term.lower()
    if label_lower == term_lower:
        return 0
    if label_lower.startswith(term_lower):
        return 1
    if term_lower in label_lower:
        return 2
    if term_lower in desc.lower():
        return 3
    return 4


# The source of an option (#142): the word of its badge, by the prefix of its ID, with
# the badge's background and text colours (light, with the word: colour alone is not
# accessible)
_SOURCE_TAGS = {'mardi': 'mardi', 'wikidata': 'wikidata', 'user': 'project', 'new': 'new', NOT_FOUND: 'new'}
_BADGES = {'mardi': ('#dbe9ff', '#1a3d7c'), 'wikidata': ('#dcf3e3', '#1e5e33'),
           'project': ('#fff1cc', '#7a5a00'), 'new': ('#ece3fb', '#4b2c83')}
# Hides the plain text of a laid-out option (RDMO shows the text, then the help); a browser
# without :has() shows both, the text stays readable
_HIDE_TEXT = ('<style>.interview-select-option:has(.mardmo-option) > span:first-child {display: none}'
              '.interview-select-option:has(.mardmo-option) > span.ml-10 {margin-left: 0}</style>')


def option_help(identifier, text):
    '''Return the help of a dropdown option for the item *identifier* with the text *text*: its layout (#142).

    A badge with the source (``mardi``, ``wikidata``, ``project`` for an
    item of the user's own in the project, ``new`` for a new item: typed in
    a relation, ``not found``, or a new publication, ``new:doi:…``), the
    label in bold and the description in grey italics on a second line.
    RDMO renders the help of an option as HTML in the open dropdown only,
    after its text; a CSS rule hides the text there.  The text stays
    ``"Label (Description)"``: it is what RDMO stores and shows in the
    filled field, and what screen readers announce.  ``''`` for an option
    without source (e.g. "new item").
    '''
    tag = _SOURCE_TAGS.get((identifier or '').split(':', 1)[0])
    if not tag or (identifier == NOT_FOUND and text == NEW_ITEM):
        return ''
    background, colour = _BADGES[tag]
    label, description, _ = extract_parts(text or '')
    layout = (f'<span class="mardmo-option"><span style="display:inline-block;background:{background};'
              f'color:{colour};border-radius:3px;padding:0 5px;margin-right:6px;font-size:80%;'
              f'vertical-align:1px">{tag}</span><span style="font-weight:600">{html.escape(label)}</span>')
    if description and description != 'No Description Provided!':
        layout += (f'<br><span style="color:#6c757d;font-style:italic;font-size:90%;margin-left:2px">'
                   f'{html.escape(description)}</span>')
    return f'{_HIDE_TEXT}{layout}</span>'
