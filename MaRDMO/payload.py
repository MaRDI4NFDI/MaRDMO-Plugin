'''Wikibase REST API payload builder for MaRDMO exports.

Provides :class:`GeneratePayload`, which transforms a prepared answers dict
into a fully structured payload dict ready for posting to the MaRDI Portal:

- Builds ``Item*`` entries for every unique entity (labels, descriptions,
  aliases, statements, qualifiers).
- Builds ``RELATION_*`` entries for cross-item statements that reference
  other items by their temporary ``Item<n>`` placeholder.
- Builds ``ALIAS_*`` entries for alias additions to existing portal items.

Key methods: :meth:`~GeneratePayload.add_data_properties`,
:meth:`~GeneratePayload.add_aliases`,
:meth:`~GeneratePayload.check_existing_relations`.
'''

import json
import logging

from dataclasses import dataclass, field
from typing import Optional

import re
import time

import requests

from .helpers import commit_writes
from .duplicates import item_source, look_up
from .ids import item_key
from .markers import MARKER_PROPERTIES, PUBLICATION_MARKERS
from .patterns import QUANTITY_AMOUNT_RE
from .queries import (
    EXPORT_CHECK_DEADLINE,
    EXPORT_RETRY_WAITS,
    request_with_retry,
)
from .validators import (
    REPOSITORY_URL_SCHEMES, WEB_URL_SCHEMES, doi_problem, normalize_formula, swmath_problem, url_problem,
)

_logger = logging.getLogger(__name__)

# Datatypes whose values the portal stores as single-line text
_TEXT_TYPES = ('string', 'external-id', 'url', 'URL', 'monolingualtext')

_QID_RE = re.compile(r'^Q\d+$')
# Placeholder of an item of the export, replaced by its QID while posting
_ITEM_KEY_RE = re.compile(r'^Item\d{10}$')
_TIME_RE = re.compile(r'^\+?(-?\d+)-(\d{2})-(\d{2})(T.*)$')
# Invisible whitespace the portal rejects; replaced by spaces on export
_INVISIBLE_WHITESPACE_RE = re.compile(r'[\t\v\f]')

# Qualifiers that give a statement its meaning: the same subject, property and
# object with another (or no) value of these is a statement of its own.  All
# other qualifiers add information and are added to an existing statement.
_MEANING_QUALIFIERS = ('object has role', 'symbol represents', 'platform')
# Item-valued properties MaRDMO writes with a meaning qualifier ("contains"
# and "described by source" with a role, "uses" with a platform).  The existence
# check also finds a portal statement with such a qualifier for one without,
# so found statements of these are checked again.  Formulas ("in defining
# formula") have their own check that compares the qualifiers.
_MEANING_PROPERTIES = ('contains', 'described by source', 'uses')
# Class of new authors and journals of publications (kind, see helpers.PART_KINDS)
_NEW_ITEM_CLASS = {'author': 'Author', 'journal': 'Journal'}


def _text_of(value):
    '''Return the text part of a plain or monolingual-text value, else ``None``.'''
    if isinstance(value, dict):
        value = value.get('text')
    return value if isinstance(value, str) else None


def _clean_text(text):
    '''Replace tabs with spaces and strip leading/trailing whitespace.

    The portal rejects both; neither changes the meaning of the text.
    Line breaks are left alone (blocked by the validator and the checks).
    '''
    return _INVISIBLE_WHITESPACE_RE.sub(' ', text).strip()


def _strip_text(value, data_type):
    '''Apply :func:`_clean_text` to text values and put formulas on one line.

    Values of other datatypes are returned unchanged.
    '''
    if data_type == 'math' and isinstance(value, str):
        return normalize_formula(value)
    if data_type not in _TEXT_TYPES:
        return value
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict) and isinstance(value.get('text'), str):
        return {**value, 'text': _clean_text(value['text'])}
    return value


def quantity_amount(text):
    '''Return *text* as a Wikibase quantity amount (``"08"`` → ``"+8"``, ``" 1.50"`` → ``"+1.50"``).

    Strips whitespace and leading zeros of plain decimals; anything else is
    passed through with a ``+`` so that :meth:`GeneratePayload.validate_identifiers`
    reports it instead of the portal rejecting it during the upload.
    '''
    text = str(text or '').strip()
    integer, dot, fraction = text.partition('.')
    if integer.isascii() and integer.isdigit() and (not dot or (fraction.isascii() and fraction.isdigit())):
        integer = integer.lstrip('0') or '0'
        return f"+{integer}{dot}{fraction}"
    return f"+{text}"


class DocumentationProblem(ValueError):
    '''The documentation cannot be exported as it is; the user has to change it.

    Raised during the export, after the checks, for problems that show only
    in the payload or against the MaRDI Portal (e.g. an item that exists
    already, a symbol that stands for another quantity there).
    '''


class PortalUnavailable(ValueError):
    '''The MaRDI Portal did not answer a check the export needs; nothing was exported.'''


@dataclass
class PayloadState:
    '''Data Class to store the current state of the Payload.'''
    counter: int = 0
    dictionary: dict = field(default_factory=dict)
    subject: dict = field(default_factory=dict)
    subject_item: Optional[str] = None

class GeneratePayload:
    '''Class to build the Payload for an Export to a Wikibase
       with Items, Statements, Qualifiers, and Checks.'''

    def __init__(
        self,
        url: str,
        user_items: dict | None = None,
        wikibase: dict | None = None,
        dependency: dict | None = None
    ):
        '''Initialise the payload builder.

        Args:
            url:         Base URL of the target Wikibase instance (e.g.
                         ``"https://portal.mardi4nfdi.de"``).
            user_items:  Mapping of temporary ``"Item<n>"`` keys to item
                         dicts ``{ID, Name, Description}``.  Produced by
                         :func:`~MaRDMO.helpers.unique_items`.
            wikibase:    Wikibase vocabulary dicts.  Expected keys are
                         ``items``, ``properties``, ``relations``, and
                         optionally ``data_properties``.
            dependency:  Dependency graph ``{item_key: set_of_dependencies}``
                         that controls item-creation order during export.
        '''
        # Input Attributes
        self.url: str = url
        self.user_items: dict = user_items
        self.wikibase: dict =  wikibase
        self.dependency: dict= dependency
        # Working Attributes
        self.state: PayloadState = PayloadState()
        # (name, description) → QID of an existing portal item, or None
        # Markers of the existing items on the portal (_find_on_portal)
        self.portal_markers: dict = {}
        self.markers_known = False
        # Item ID → the sections whose markers it got (markers.SECTION_MARKERS)
        self.marked: dict = {}
        # QID → claims of portal items fetched during this export
        self._claims: dict = {}

    def _items_url(self):
        '''Return the Wikibase REST API endpoint URL for creating new items.'''
        return f'{self.url}/w/rest.php/wikibase/v1/entities/items'

    def _statement_url(self, item):
        '''Return the Wikibase REST API endpoint URL for adding statements to *item*.

        Args:
            item: Wikibase QID string (e.g. ``"Q42"``).
        '''
        return f'{self.url}/w/rest.php/wikibase/v1/entities/items/{item}/statements'

    def _alias_url(self, item):
        '''Return the Wikibase REST API endpoint URL for adding English aliases to *item*.

        Args:
            item: Wikibase QID string (e.g. ``"Q42"``).
        '''
        return f'{self.url}/w/rest.php/wikibase/v1/entities/items/{item}/aliases/en'

    def _build_item(self, identifier, label, description, statements = None):
        '''Build the payload dict for a new or existing Wikibase item.

        Args:
            identifier:  Existing Wikibase QID (empty string for new items).
            label:       English label string.
            description: English description string.
            statements:  Optional list of statement triples; defaults to ``[]``.

        Returns:
            Dict with keys ``id``, ``url``, ``label``, ``description``,
            and ``statements``.
        '''
        # Empty Statements if none provided
        if statements is None:
            statements = []
        if description == "No Description Provided!":
            description = ""
        label = _clean_text(label) if isinstance(label, str) else label
        description = _clean_text(description) if isinstance(description, str) else description
        # Build Item
        item = {'id': identifier,
                'url': self._items_url(),
                'label': label,
                'description':  description,
                'statements': statements}
        return item

    def _build_statement(self, identifier, content, data_type = "wikibase-item", qualifiers = None):
        '''Build the Wikibase REST API statement payload dict.

        Args:
            identifier:  Wikibase property ID string (e.g. ``"P31"``).
            content:     Statement value (QID, string, or typed literal).
            data_type:   Wikibase datatype string (default ``"wikibase-item"``).
            qualifiers:  Optional list of qualifier dicts; defaults to ``[]``.

        Returns:
            Dict in the shape expected by the Wikibase REST API
            ``POST .../statements`` endpoint.
        '''
        # Empty Qualifiers if none provided
        if qualifiers is None:
            qualifiers = []
        # Build Statement
        statement = {"statement":
                        {"property":
                            {"id": identifier,
                             "data_type": data_type},
                             "value":
                                {"type": "value",
                                 "content": content},
                             "qualifiers": qualifiers
                        }
                    }
        return statement

    def _build_alias(self, alias):
        '''Wrap *alias* in the ``{"aliases": …}`` payload dict expected by the API.

        Args:
            alias: List of alias strings.

        Returns:
            Dict ``{"aliases": alias}``.
        '''
        aliases_dict = {
          "aliases": alias
        }
        return aliases_dict

    def _normalize_aliases(self, aliases_dict: dict) -> list[str]:
        '''Convert a ``{index: alias}`` dict to a sorted, deduplicated list of strings.

        Args:
            aliases_dict: Dict mapping integer-like keys to alias strings.

        Returns:
            List of non-blank alias strings in ascending key order.
        '''
        return [
            _clean_text(a) for _, a in sorted(aliases_dict.items())
            if isinstance(a, str) and a.strip()
        ]

    def _resolve_item_reference(self, value):
        '''Replace an ``Item<n>`` placeholder by its QID.

        Returns the QID, *value* unchanged when it is not a placeholder, or
        ``''`` when the placeholder refers to an item that does not exist yet.
        '''
        if isinstance(value, str) and value in self.state.dictionary:
            return self.state.dictionary[value].get('id', '')
        return value

    def _meaning_qualifiers(self):
        '''Property IDs of the qualifiers that give a statement its meaning.'''
        properties = self.wikibase['properties']
        return {properties[name] for name in _MEANING_QUALIFIERS if name in properties}

    def _find_key_by_values(self, id_value, name_value, description_value):
        '''Look up the ``"Item<n>"`` key matching the given ID, Name, and Description.

        Args:
            id_value:          ``ID`` field value to match.
            name_value:        ``Name`` field value to match.
            description_value: ``Description`` field value to match.

        Returns:
            Matching ``"Item<n>"`` key string, or ``None`` if not found.
        '''
        wanted = item_key(id_value, name_value, description_value)
        for key, values in self.user_items.items():
            if item_key(values['ID'], values['Name'], values['Description']) == wanted:
                return key
        return None

    def get_dictionary(self):
        '''Return the complete payload dictionary (items, relations, and aliases).

        The returned dict maps ``"Item<n>"``, ``"RELATION<n>"``, and
        ``"ALIAS<n>"`` keys to their respective payload entries.  This is the
        top-level structure posted to the Wikibase REST API by
        :class:`~MaRDMO.oauth2.OauthProviderMixin`.
        '''
        # Get Target Dictionary
        target_dictionary = self.state.dictionary
        return target_dictionary

    def subject_markers(self):
        """The portal markers of the current subject (#141, see :meth:`_find_on_portal`).

        Returns:
            ``None`` for a new item; for an existing one ``{'class': set,
            'community': set, 'profile': set}`` of QIDs, or ``False`` if its
            markers could not be looked up.
        """
        qid = self.state.dictionary.get(self.state.subject_item, {}).get('id')
        if not qid:
            return None
        markers = self.portal_markers.get(qid) if self.markers_known else None
        return markers if markers is not None else False

    def get_item_key(self, value, role='subject'):
        """Look up the ``"Item<n>"`` key for *value* and optionally set it as the current subject.

        Args:
            value: Item dict with ``ID``, ``Name``, and ``Description`` fields.
            role:  ``'subject'`` (default) stores the item as the active
                   subject for subsequent :meth:`add_answer` calls;
                   ``'object'`` just returns the key without updating state.

        Returns:
            The ``"Item<n>"`` key string for *value*.

        Raises:
            DocumentationProblem: If *value* is empty or missing ``Name``/``Description``.
        """
        if not value:
            raise DocumentationProblem("Missing Item in Statement!")
        if not value.get('Name') or not value.get('Description'):
            raise DocumentationProblem("All Items need to have a 'Name' and 'Description'!")

        item_key = self._find_key_by_values(
            value['ID'],
            value['Name'],
            value['Description'],
        )

        if role == 'subject':
            self.state.subject = value
            self.state.subject_item = item_key

        return item_key

    def set_class(self, name: str) -> None:
        '''Tag the current subject item with an entity-class label.

        Used by ``_export_*`` worker methods so that :func:`~MaRDMO.helpers.compare_items`
        can include the class in its output for grouping on the success page.

        Args:
            name: Human-readable class label (e.g. ``'Mathematical Model'``).
        '''
        if self.state.subject_item:
            self.state.dictionary[self.state.subject_item]['class'] = name

    def add_qualifier(self, identifier, data_type, content):
        '''Build a single-qualifier list for use in :meth:`add_answer`.

        Args:
            identifier: Wikibase property ID string for the qualifier (e.g. ``"P3"``).
            data_type:  Wikibase datatype string for the qualifier value.
            content:    Qualifier value (QID, string, or typed literal).

        Returns:
            Single-element list containing the qualifier dict, or an empty
            list when a text value is empty after stripping whitespace.
        '''
        content = _strip_text(content, data_type)
        if data_type in _TEXT_TYPES and not _text_of(content):
            return []
        # Build Qualifer
        qualifier = [{"property":
                        {"id": identifier,
                         "data_type": data_type},
                         "value": 
                            {"type": "value",
                             "content": content}
                    }]
        return qualifier

    def add_data_properties(self, item_class):
        '''Add ``instance of`` statements for each data property selected on the current subject.

        Looks up the data-property URL → QID mapping for *item_class* and
        calls :meth:`add_answer` for every property value stored in
        ``subject["Properties"]``.

        Args:
            item_class: Entity class string passed to
                        ``self.wikibase["data_properties"]`` (e.g. ``"model"``).
        '''
        data_properties = self.wikibase['data_properties'](item_class)
        for prop in self.state.subject.get('Properties', {}).values():
            self.add_answer(
                verb=self.wikibase['properties']['instance of'],
                object_and_type=[
                    data_properties[prop],
                    'wikibase-item',
                ]
            )

    def validate_identifiers(self):
        '''Reject malformed URLs, DOIs, swMATH IDs, dates and amounts before anything is posted.

        Applies the strict rules from :mod:`~MaRDMO.validators` to every URL
        statement and qualifier and to every "DOI" and "swMath work ID" value,
        checks that every time value is a ``+YYYY-MM-DDThh:mm:ssZ`` string and
        every quantity amount a Wikibase decimal (``+8``, ``+1.5``).
        This catches values that bypassed the pre-save validator, the preview
        and the checks, so an export never fails halfway because of them.

        Raises:
            DocumentationProblem: One argument per invalid value, naming item and property.
            ValueError: One argument per placeholder without item (an internal error).
        '''
        properties = self.wikibase['properties']
        pid_to_name = {pid: name for name, pid in properties.items()}
        repository_pid = properties.get('source code repository URL')
        doi_pid = properties.get('DOI')
        swmath_pid = properties.get('swMath work ID')
        errors = []

        def check(item_name, prop_id, data_type, value):
            if data_type == 'quantity':
                text = str(value.get('amount', '')) if isinstance(value, dict) else str(value)
                if not QUANTITY_AMOUNT_RE.match(text):
                    errors.append(f'"{item_name}", {pid_to_name.get(prop_id, prop_id)}: '
                                  f'invalid number ("{text.lstrip("+")}")')
                return
            if data_type == 'time':
                text = value.get('time', '') if isinstance(value, dict) else str(value)
                if not _TIME_RE.match(text):
                    errors.append(f'"{item_name}", {pid_to_name.get(prop_id, prop_id)}: '
                                  f'invalid date ("{text}")')
                return
            text = value if isinstance(value, str) else ''
            if not text:
                return
            if prop_id == doi_pid:
                problem = doi_problem(text)
            elif prop_id == swmath_pid:
                problem = swmath_problem(text)
            else:
                schemes = REPOSITORY_URL_SCHEMES if prop_id == repository_pid else WEB_URL_SCHEMES
                problem = url_problem(text, schemes)
            if problem:
                shown = text if len(text) <= 60 else f'{text[:57]}...'
                errors.append(f'"{item_name}", {pid_to_name.get(prop_id, prop_id)}: {problem} ("{shown}")')

        def relevant(prop_id, data_type):
            return data_type in ('url', 'URL', 'time', 'quantity') or prop_id in (doi_pid, swmath_pid)

        def check_statement(item_name, prop_id, data_type, value, qualifiers):
            if relevant(prop_id, data_type):
                check(item_name, prop_id, data_type, value)
            for qualifier in qualifiers or []:
                q_type = qualifier['property']['data_type']
                if relevant(qualifier['property']['id'], q_type):
                    check(item_name, qualifier['property']['id'], q_type, qualifier['value']['content'])

        for key, entry in self.state.dictionary.items():
            if key.startswith('Item'):
                for statement in entry.get('statements', []):
                    check_statement(
                        entry.get('label') or key, statement[0], statement[1], statement[2],
                        statement[3] if len(statement) > 3 else [],
                    )
            elif key.startswith('RELATION'):
                item_key = entry['url'].split('/items/')[1].split('/')[0]
                statement = entry['payload']['statement']
                check_statement(
                    self.state.dictionary.get(item_key, {}).get('label') or item_key,
                    statement['property']['id'], statement['property']['data_type'],
                    statement['value']['content'], statement.get('qualifiers', []),
                )

        if errors:
            raise DocumentationProblem(*errors)
        dangling = self._dangling_references()
        if dangling:
            # an internal error, not the user's: a plain ValueError
            raise ValueError(*dangling)

    def _dangling_references(self):
        '''Messages for ``Item<n>`` placeholders that refer to no item of the export.

        Every placeholder is replaced by the QID of its item while posting; one
        without an item would reach the portal as a value it rejects, after
        other items may have been created already.
        '''
        found = []

        def walk(value, owner):
            if isinstance(value, dict):
                for inner in value.values():
                    walk(inner, owner)
            elif isinstance(value, (list, tuple)):
                for inner in value:
                    walk(inner, owner)
            elif isinstance(value, str) and _ITEM_KEY_RE.match(value) and value not in self.state.dictionary:
                found.append(f'"{owner}": refers to an item that is not part of the export ({value}); '
                             'nothing was exported, please report this to the MaRDMO developers')

        for key, entry in self.state.dictionary.items():
            if key.startswith('Item'):
                walk(entry.get('statements', []), entry.get('label') or key)
            else:
                # RELATION and ALIAS entries: the subject in the URL and the payload
                item_key = entry.get('url', '').split('/items/')[-1].split('/')[0]
                owner = self.state.dictionary.get(item_key, {}).get('label') or item_key
                walk([item_key, entry.get('payload', {})], owner)
        return list(dict.fromkeys(found))

    def check_existing_relations(self, api_url):
        '''Mark every RELATION entry that already exists on the portal.

        Fetches the claims of the existing items the RELATION entries belong
        to (wbgetentities, 50 items per request) and decides each entry with
        :meth:`exists_in_claims`.  The qualifier merge and the symbol check
        use the same claims.  Failed requests are retried after
        :data:`~MaRDMO.queries.EXPORT_RETRY_WAITS`; all of them together give
        up after :data:`~MaRDMO.queries.EXPORT_CHECK_DEADLINE` seconds.

        Args:
            api_url: Action API URL of the portal.

        Raises:
            PortalUnavailable: If the claims cannot be fetched.  Posting without
                the check would duplicate statements on existing items.
        '''
        relations = {key: entry for key, entry in self.state.dictionary.items() if key.startswith('RELATION')}
        if not relations:
            return

        deadline = time.monotonic() + EXPORT_CHECK_DEADLINE
        subjects = {self._resolve_item_reference(entry['url'].split('/')[-2]) for entry in relations.values()}
        claims = self._fetch_claims(
            sorted(s for s in subjects if isinstance(s, str) and _QID_RE.match(s)), api_url, deadline, 'statements',
        )
        for entry in relations.values():
            entry['exists'] = self.exists_in_claims(entry, claims)

        # Statements that only add qualifiers (e.g. another assumption) extend
        # the portal statement instead of duplicating it
        self.merge_qualifiers(api_url, deadline)
        # Symbols of formulas: complete a symbol without quantity, stop if it
        # stands for another quantity
        self.check_symbols(api_url, deadline)

    def exists_in_claims(self, entry, claims):
        '''``'true'`` if the portal item of the RELATION *entry* holds its statement, else ``'false'``.

        The statement is there if a claim of the item has the property, the
        value and every qualifier of *entry* (:meth:`_snak_matches`).  A claim
        with more qualifiers matches too; :meth:`merge_qualifiers` decides
        afterwards on the qualifiers that give a statement its meaning.  A
        statement of a new item, or with a value or qualifier that is a new
        item, is new.

        Args:
            entry:  RELATION entry of ``self.state.dictionary``.
            claims: ``{qid: claims}`` of the portal items (:meth:`_fetch_claims`).
        '''
        statement = entry['payload']['statement']
        subject = self._resolve_item_reference(entry['url'].split('/')[-2])
        if not (isinstance(subject, str) and _QID_RE.match(subject)):
            return 'false'
        value = self._resolve_item_reference(statement['value']['content'])
        data_type = statement['property']['data_type']
        wanted = [(q['property']['id'], self._resolve_item_reference(q['value']['content']),
                   q['property']['data_type']) for q in statement.get('qualifiers', [])]
        if value == '' or any(q_value == '' for _, q_value, _ in wanted):
            return 'false'
        for claim in claims.get(subject, {}).get(statement['property']['id'], []):
            if not self._snak_matches(claim.get('mainsnak', {}), value, data_type):
                continue
            if all(any(self._snak_matches(snak, q_value, q_type) for snak in claim.get('qualifiers', {}).get(q_prop, []))
                   for q_prop, q_value, q_type in wanted):
                return 'true'
        return 'false'

    def _fetch_claims(self, qids, api_url, deadline, what):
        '''Return ``{qid: claims}`` of portal items, fetched with wbgetentities in chunks of 50.

        Items fetched before during this export are taken from the earlier
        answer (the existence check, the qualifier merge and the symbol check need the same).

        Raises:
            PortalUnavailable: If the claims cannot be fetched; *what* names the
                checked statements in the message (e.g. ``'formulas'``).
        '''
        claims_by_item = self._claims
        qids = [qid for qid in qids if qid not in claims_by_item]
        for i in range(0, len(qids), 50):
            body = None
            try:
                resp = request_with_retry(
                    'get',
                    api_url,
                    waits=EXPORT_RETRY_WAITS,
                    deadline=deadline,
                    params={
                        'action': 'wbgetentities',
                        'ids':    '|'.join(qids[i:i + 50]),
                        'props':  'claims',
                        'format': 'json',
                    },
                    headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
                    timeout=30,
                )
                resp.raise_for_status()
                body = resp.json()
            except (requests.exceptions.RequestException, ValueError) as exc:
                _logger.warning("Claims check via API failed: %s", exc)
            if body is not None and 'error' in body:
                _logger.warning("Claims check via API failed: %s", body['error'])
                body = None
            if body is None:
                raise PortalUnavailable(
                    f"Could not check which {what} already exist on the MaRDI Portal "
                    "(API not reachable). Nothing was exported; please try again later."
                )
            for qid, entity in body.get('entities', {}).items():
                claims_by_item[qid] = entity.get('claims', {})
        return claims_by_item

    @staticmethod
    def _snak_matches(snak, value, data_type):
        '''Whether a portal snak (main value or qualifier) holds *value* of *data_type*.

        *value* is a payload value with item placeholders already resolved;
        an unresolved placeholder (``''``, an item created in this export)
        never matches.
        '''
        if value == '' or 'datavalue' not in snak:
            return False
        api = snak['datavalue'].get('value')
        if data_type == 'wikibase-item':
            return isinstance(api, dict) and api.get('id') == value
        if data_type == 'monolingualtext':
            text, language = (value.get('text'), value.get('language', 'en')) \
                if isinstance(value, dict) else (value, 'en')
            return isinstance(api, dict) and api.get('text') == text and api.get('language') == language
        if data_type == 'quantity':
            if not (isinstance(api, dict) and isinstance(value, dict)):
                return False
            same_unit = str(api.get('unit', '1')).rsplit('/', 1)[-1] == \
                str(value.get('unit', '1')).rsplit('/', 1)[-1]
            return same_unit and str(api.get('amount', '')).lstrip('+') == \
                str(value.get('amount', '')).lstrip('+')
        if data_type == 'time':
            return isinstance(api, dict) and isinstance(value, dict) \
                and api.get('time') == value.get('time') \
                and api.get('precision') == value.get('precision', api.get('precision'))
        return api == value

    @staticmethod
    def _same_meaning(entry_meaning, claim_meaning, role):
        '''Whether a portal statement's meaning qualifiers give it the meaning of the entry.

        Both are sets of ``(property ID, value)``.  Roles (*role*, the "object
        has role" property) are contained: a portal statement "as initial
        value and parameter" is also the one "as parameter" (MaRDMO writes one
        role per statement and imports such a statement as a relation for
        each role the questionnaire offers).  No role matches no role only.
        The other meaning qualifiers (symbol represents, platform) must be
        the same.
        '''
        entry_roles = {q for q in entry_meaning if q[0] == role}
        claim_roles = {q for q in claim_meaning if q[0] == role}
        if entry_meaning - entry_roles != claim_meaning - claim_roles:
            return False
        return entry_roles == claim_roles or bool(entry_roles) and entry_roles <= claim_roles

    def merge_qualifiers(self, api_url, deadline=None):
        '''Turn new statements that only add qualifiers into additions to the portal statement.

        For every RELATION entry not found on the portal: if its item already
        holds a statement with the same property, value and the same
        qualifiers that give it its meaning (role, symbol represents,
        platform; also when there is none; the entry's roles may be some of
        the statement's, see :meth:`_same_meaning`), the entry is marked ``'partial'``
        with that statement's ID and the qualifiers it lacks, so posting adds
        them to the statement instead of writing it a second time.  An entry
        whose qualifiers are all there already is marked ``'true'``.  Several
        entries adding to the same statement share it; a qualifier is planned
        only once.

        Entries the existence check found are checked again when their property
        can carry a meaning qualifier (see :data:`_MEANING_PROPERTIES`): the
        portal statement it found may have one the entry lacks (a plain
        "contains" against "contains" with a role).  Without a statement of
        the same meaning they are new.

        Raises:
            ValueError: If the claims of an existing item cannot be fetched.
        '''
        meaning = self._meaning_qualifiers()
        role = self.wikibase['properties'].get('object has role')
        # Properties whose statements can carry a meaning qualifier: a statement
        # found by the existence check may have one the payload statement lacks
        # (e.g. "contains" with a role for a plain "contains"), also when no
        # statement of this export has one
        properties = self.wikibase['properties']
        with_meaning = {properties[name] for name in _MEANING_PROPERTIES if name in properties} | {
            statement[0] for entry in self.state.dictionary.values()
            for statement in entry.get('statements') or []
            if len(statement) > 3 and any(q['property']['id'] in meaning for q in statement[3])
        } | {
            entry['payload']['statement']['property']['id']
            for key, entry in self.state.dictionary.items() if key.startswith('RELATION')
            and any(q['property']['id'] in meaning for q in entry['payload']['statement'].get('qualifiers', []))
        }
        candidates = []
        for key, entry in self.state.dictionary.items():
            if not key.startswith('RELATION'):
                continue
            statement = entry['payload']['statement']
            if entry.get('exists') == 'true' and statement['property']['id'] not in with_meaning:
                continue
            subject = self._resolve_item_reference(entry['url'].split('/')[-2])
            value = self._resolve_item_reference(statement['value']['content'])
            if not (isinstance(subject, str) and _QID_RE.match(subject)) or value == '':
                continue        # new item: the statement cannot exist yet
            qualifiers = statement.get('qualifiers', [])
            meaning_values = {
                (q['property']['id'], json.dumps(self._resolve_item_reference(q['value']['content']),
                                                 sort_keys=True))
                for q in qualifiers if q['property']['id'] in meaning
            }
            added = [q for q in qualifiers if q['property']['id'] not in meaning]
            if any(v == '""' for _, v in meaning_values):
                continue        # its meaning refers to a new item: a new statement
            if not added and entry.get('exists') != 'true':
                continue        # nothing to add: a new statement
            candidates.append((key, subject, statement, value, meaning_values, added))
        if not candidates:
            return

        claims_by_item = self._fetch_claims(
            sorted({c[1] for c in candidates}), api_url, deadline, 'statements',
        )
        planned = {}    # statement ID -> qualifiers already planned for it
        for key, subject, statement, value, meaning_values, added in candidates:
            prop_id, data_type = statement['property']['id'], statement['property']['data_type']
            best = None
            for claim in claims_by_item.get(subject, {}).get(prop_id, []):
                if not self._snak_matches(claim.get('mainsnak', {}), value, data_type):
                    continue
                claim_meaning = {
                    (q_prop, json.dumps(snak['datavalue']['value'].get('id')
                                        if isinstance(snak['datavalue']['value'], dict)
                                        and 'id' in snak['datavalue']['value']
                                        else snak['datavalue']['value'], sort_keys=True))
                    for q_prop, snaks in claim.get('qualifiers', {}).items() if q_prop in meaning
                    for snak in snaks if 'datavalue' in snak
                }
                if not self._same_meaning(meaning_values, claim_meaning, role):
                    continue
                missing = [
                    q for q in added
                    if not any(self._snak_matches(snak, self._resolve_item_reference(q['value']['content']),
                                                  q['property']['data_type'])
                               for snak in claim.get('qualifiers', {}).get(q['property']['id'], []))
                    and json.dumps(q, sort_keys=True) not in planned.get(claim['id'], set())
                ]
                # Fewest qualifiers to add; of those, a statement with exactly these roles
                rank = (len(missing), claim_meaning != meaning_values)
                if best is None or rank < best[2]:
                    best = (claim['id'], missing, rank)
            entry = self.state.dictionary[key]
            if best is None:
                # no statement with this meaning on the portal: a new one (also
                # when the existence check found one with another meaning)
                entry['exists'] = 'false'
                continue
            if not best[1]:
                entry['exists'] = 'true'
                continue
            entry['exists'] = 'partial'
            entry['statement_id'] = best[0]
            entry['add_qualifiers'] = best[1]
            planned.setdefault(best[0], set()).update(json.dumps(q, sort_keys=True) for q in best[1])

    def check_symbols(self, api_url, deadline=None):
        '''Compare new "in defining formula" statements with the symbols of the item on the portal.

        A symbol stands for exactly one quantity of its formula or quantity
        (the checks ensure this within the questionnaire).  For every such
        statement not on the portal yet, the statements of the same item
        with the same symbol decide:

        - one with another quantity: the export stops, MaRDMO cannot change
          what the symbol stands for (e.g. a symbol block of a fetched
          formula deleted and added again with another quantity);
        - one without a quantity (no "symbol represents"): it gets the
          quantity (``'partial'``) instead of a second statement;
        - none: a new statement.

        Raises:
            DocumentationProblem: One argument per symbol that stands for another
                quantity on the portal.
            PortalUnavailable: If the claims cannot be fetched.
        '''
        properties = self.wikibase['properties']
        in_formula, represents = properties.get('in defining formula'), properties.get('symbol represents')
        if not in_formula or not represents:
            return
        entries = []
        for key, entry in self.state.dictionary.items():
            if not key.startswith('RELATION') or entry.get('exists') != 'false':
                continue
            statement = entry['payload']['statement']
            if statement['property']['id'] != in_formula:
                continue
            subject = self._resolve_item_reference(entry['url'].split('/')[-2])
            quantity = [q for q in statement.get('qualifiers', []) if q['property']['id'] == represents]
            if not (isinstance(subject, str) and _QID_RE.match(subject)) or len(quantity) != 1:
                continue
            entries.append((key, subject, statement['value']['content'], quantity[0]))
        if not entries:
            return

        claims_by_item = self._fetch_claims(sorted({e[1] for e in entries}), api_url, deadline, 'formulas')
        labels = {e.get('id'): e.get('label') for k, e in self.state.dictionary.items()
                  if k.startswith('Item') and e.get('id')}
        conflicts, taken = [], set()
        for key, subject, symbol, qualifier in entries:
            quantity = self._resolve_item_reference(qualifier['value']['content'])
            same_symbol = [
                (claim, {snak['datavalue']['value'].get('id')
                         for snak in claim.get('qualifiers', {}).get(represents, [])
                         if isinstance(snak.get('datavalue', {}).get('value'), dict)})
                for claim in claims_by_item.get(subject, {}).get(in_formula, [])
                if claim.get('mainsnak', {}).get('datavalue', {}).get('value') == symbol
            ]
            entry = self.state.dictionary[key]
            if quantity and any(quantity in found for _, found in same_symbol):
                entry['exists'] = 'true'
                continue
            other = sorted({qid for _, found in same_symbol for qid in found})
            if other:
                shown = ', '.join(f'{qid} ({labels[qid]})' if labels.get(qid) else qid for qid in other)
                conflicts.append(
                    f'"{labels.get(subject) or subject}" ({subject}): on the MaRDI Portal the symbol {symbol} '
                    f'already stands for {shown}. MaRDMO cannot change this: use that quantity for the '
                    'symbol, or correct it on the MaRDI Portal.'
                )
                continue
            incomplete = next((claim for claim, found in same_symbol
                               if not found and claim['id'] not in taken), None)
            if incomplete is not None:
                taken.add(incomplete['id'])
                entry['exists'] = 'partial'
                entry['statement_id'] = incomplete['id']
                entry['add_qualifiers'] = [qualifier]
        if conflicts:
            raise DocumentationProblem(*conflicts)

    def add_aliases(self, aliases_dict):
        '''Add aliases for the current subject to the payload.

        For existing items (with a real QID), creates ``ALIAS`` entries for
        immediate posting.  For new items, stores the aliases on the pending
        item entry for batch creation.

        Args:
            aliases_dict: ``{index: alias_string}`` dict; does nothing when empty.
        '''
        if not aliases_dict:
            return
        aliases_list = self._normalize_aliases(aliases_dict)
        # Add Aliases
        if (
            self.state.dictionary[self.state.subject_item]['id']
        ):
            self._add_alias(
                item = self.state.subject_item,
                aliases = aliases_list
            )
        else:
            self._add_to_item_alias(
                item = self.state.subject_item,
                aliases = aliases_list
            )

    def add_answer(self, verb, object_and_type,
                   qualifier = None, subject = None):
        '''Add a single statement to the payload.

        For items that already exist on the portal (have a real QID), a
        ``RELATION`` entry is created.  For new items, the statement is
        appended to the item's ``statements`` list for batch creation.

        Args:
            verb:            Wikibase property ID string (e.g. ``"P31"``).
            object_and_type: Two-element list ``[value, datatype]`` where
                             *datatype* is a Wikibase type string such as
                             ``"wikibase-item"``, ``"string"``, or ``"math"``.
            qualifier:       Optional list of qualifier dicts built by
                             :meth:`add_qualifier`.
            subject:         ``"Item<n>"`` key of the subject item; defaults
                             to the current subject set by :meth:`get_item_key`.
        '''
        if subject is None:
            subject = self.state.subject_item
        if qualifier is None:
            qualifier = []
        value = _strip_text(object_and_type[0], object_and_type[1])
        if object_and_type[1] in _TEXT_TYPES and not _text_of(value):
            return
        # Gather Statement
        statement = {
            'property_id': verb,
            'datatype': object_and_type[1],
            'value': value
        }
        # Pattern of New Item
        pattern = re.compile(r"^Item\d{10}$")
        # Add Relation
        if (
            self.state.dictionary[subject]['id']
        ):
            self._add_relation(
                item=subject,
                statement=statement,
                qualifier=qualifier
            )
        else:
            if (isinstance(statement['value'], str) and pattern.match(statement['value'])):
                self.dependency[subject].add(statement['value'])
            self._add_to_item_statement(
                item=subject,
                statement=statement,
                qualifier=qualifier
            )

    def add_answers(self, mardmo_property, wikibase_property, datatype = 'string'):
        '''Add one statement per entry in ``subject[mardmo_property]``.

        Iterates over all values stored under *mardmo_property* in the
        current subject dict and calls :meth:`add_answer` for each.

        Args:
            mardmo_property:  Key in the subject dict (e.g. ``"descriptionLong"``).
            wikibase_property: Wikibase property label looked up in
                               ``self.wikibase['properties']``.
            datatype:          Wikibase value datatype (default ``"string"``).
        '''
        for entry in self.state.subject.get(mardmo_property, {}).values():
            self.add_answer(
                verb=self.wikibase['properties'][wikibase_property],
                object_and_type=[
                    entry,
                    datatype,
                ]
            )

    def add_single_relation(
        self,
        statement,
        alt_statement = None,
        qualifier = None,
        reverse = False
    ):
        '''Add one statement per entry in ``subject[statement["relatant"]]``.

        If the relatant item exists in the payload dictionary, uses
        ``statement['relation']`` as the property; otherwise falls back to
        *alt_statement* with a string value, or adds nothing without one
        (e.g. a journal the export left out).

        Args:
            statement:     Dict with ``relation`` (property ID) and
                           ``relatant`` (subject key) fields.
            alt_statement: Fallback dict used when the relatant is not in
                           the payload (optional).
            qualifier:     Pre-built qualifier list (optional).
            reverse:       If ``True``, the relatant becomes the subject and
                           the current item becomes the object.
        '''
        # Empty Qualifiers if none provided
        if qualifier is None:
            qualifier = []
        for entry in self.state.subject.get(statement['relatant'], {}).values():
            # Get Item Key
            entry_item = self.get_item_key(entry, 'object')
            if entry_item in self.state.dictionary:
                # Assign Object and Subject
                if reverse:
                    subject_item, object_item = entry_item, self.state.subject_item
                else:
                    subject_item, object_item = self.state.subject_item, entry_item
                # Add to Payload
                self.add_answer(
                    verb = statement['relation'],
                    object_and_type = [
                        object_item,
                        'wikibase-item',
                    ],
                    qualifier = qualifier,
                    subject = subject_item
                )
            elif alt_statement:
                # Add to Payload
                self.add_answer(
                    verb = alt_statement['relation'],
                    object_and_type = [
                        entry.get(alt_statement['relatant']),
                        'string',
                    ],
                    qualifier = qualifier
                )

    def add_multiple_relation(self, statement, optional_qualifier = None, reverse = False):
        '''Add one statement per (relation, relatant) pair in the current subject.

        Iterates over ``subject[statement["relation"]]`` and
        ``subject[statement["relatant"]]`` simultaneously, attaching the
        optional assumption qualifier (if configured by *optional_qualifier*)
        and object-role qualifiers.

        Args:
            statement:          Dict with ``relation`` and ``relatant`` keys.
            optional_qualifier: List of qualifier type strings to attach; supported
                                value: ``"assumes"``.
            reverse:            If ``True``, swap subject and object.
        '''

        if optional_qualifier is None:
            optional_qualifier = []

        for key, prop in self.state.subject.get(statement['relation'], {}).items():
            for key2 in self.state.subject.get(statement['relatant'], {}).get(key, {}):
                # Get Item Key
                relatant_item = self.get_item_key(
                    self.state.subject.get(statement['relatant'], {}).get(key, {}).get(key2, {}),
                    'object'
                )

                # Set Up Qualifier
                qualifier = []

                # Add Assumptions to Qualifier
                if 'assumes' in optional_qualifier:
                    if self.state.subject.get('assumption', {}).get(key, {}):
                        for assumption in self.state.subject['assumption'][key].values():
                            assumption_item = self.get_item_key(
                                assumption,
                                'object'
                            )
                            qualifier.extend(
                                self.add_qualifier(
                                    self.wikibase['properties']['assumes'],
                                    'wikibase-item',
                                    assumption_item
                                )
                            )

                # Add Roles to Qualifier
                if len(self.wikibase['relations'][prop]) == 2:
                    if self.wikibase['relations'][prop][1] not in ('forward', 'backward'):
                        qualifier.extend(
                            self.add_qualifier(
                                self.wikibase['properties']['object has role'],
                                'wikibase-item',
                                self.wikibase['relations'][prop][1]
                            )
                        )

                # Assign Object and Subject
                if reverse or self.wikibase['relations'][prop][-1] == 'backward':
                    subject_item, object_item = relatant_item, self.state.subject_item
                else:
                    subject_item, object_item = self.state.subject_item, relatant_item

                # Add to Payload
                self.add_answer(
                    verb = self.wikibase['relations'][prop][0],
                    object_and_type = [
                        object_item,
                        'wikibase-item',
                    ],
                    qualifier = qualifier,
                    subject = subject_item
                )

    def add_in_defining_formula(self):
        '''Add ``in defining formula`` statements with ``symbol represents`` qualifiers.

        Iterates over ``subject["element"]`` entries, looks up each quantity
        item key, and adds a ``math``-typed statement linking the symbol LaTeX
        to the quantity item via a qualifier.
        '''
        for element in self.state.subject.get('element', {}).values():
            # Get Item Key
            quantity_item = self.get_item_key(
                element.get('quantity', {}),
                'object'
            )
            # Add Quantity Qualifier
            qualifier = self.add_qualifier(
                self.wikibase['properties']['symbol represents'],
                'wikibase-item',
                quantity_item
            )
            # Pattern of New Item
            pattern = re.compile(r"^Item\d{10}$")
            # Add Symbol to Payload
            if (
                self.state.dictionary[self.state.subject_item]['id']
                or self.state.subject_item == quantity_item
            ):
                self._add_relation(
                    item = self.state.subject_item,
                    statement = {
                        'property_id': self.wikibase['properties']['in defining formula'],
                        'value': element.get('symbol', ''),
                        'datatype': 'math'
                    },
                    qualifier = qualifier
                )
            else:
                if (isinstance(quantity_item, str) and pattern.match(quantity_item)):
                    self.dependency[self.state.subject_item].add(quantity_item)
                    self.add_answer(
                        verb=self.wikibase['properties']['in defining formula'],
                        object_and_type=[
                            element.get('symbol', ''),
                            'math',
                        ],
                        qualifier=qualifier
                    )

    def _add_entry(self, key, value):
        '''Insert *value* under *key* into ``self.state.dictionary``.

        Args:
            key:   Dict key (e.g. ``"Item0000000001"``).
            value: Payload entry dict to store.
        '''
        self.state.dictionary[key] = value

    def _add_to_item_alias(self, item, aliases):
        '''Store *aliases* list on the pending item entry for *item*.'''
        self.state.dictionary[item]['aliases'] = aliases

    def _add_to_item_statement(self, item, statement, qualifier=None):
        '''Append *statement* to the pending statement list of *item*.

        Used for new items that do not yet have a Wikibase QID; statements are
        batched and created together with the item.

        Args:
            item:       ``"Item<n>"`` key of the target item.
            statement:  Dict with ``property_id``, ``datatype``, and ``value``.
            qualifier:  Optional qualifier list (default ``[]``).
        '''
        if qualifier is None:
            qualifier = []
        self.state.dictionary[item]['statements'].append(
            [
                statement['property_id'],
                statement['datatype'],
                statement['value'],
                qualifier
            ]
        )

    def _add_relation(self, item, statement, qualifier=None):
        '''Create a ``RELATION<n>`` entry for a statement on an existing item.

        Args:
            item:       Wikibase QID or ``"Item<n>"`` key of the target item.
            statement:  Dict with ``property_id``, ``datatype``, and ``value``.
            qualifier:  Optional qualifier list (default ``[]``).
        '''
        if qualifier is None:
            qualifier = []
        key = f"RELATION{self.state.counter}"
        self.state.dictionary[key] = {
            'id': '',
            'url': self._statement_url(item),
            'payload': self._build_statement(
                statement['property_id'],
                _strip_text(statement['value'], statement['datatype']),
                statement['datatype'],
                qualifier
            )
        }
        self.state.counter += 1

    def _add_alias(self, item, aliases):
        '''Create one ``ALIAS<n>`` entry per alias for an existing item.

        Args:
            item:    Wikibase QID or ``"Item<n>"`` key of the target item.
            aliases: List of alias strings to register.
        '''
        for alias in aliases:
            key = f"ALIAS{self.state.counter}"
            self.state.dictionary[key] = {
                'id': '',
                'url': self._alias_url(item),
                'payload': self._build_alias(
                    alias = [alias]
                )
            }
            self.state.counter += 1

    def add_item_payload(self):
        '''Finalise the ``payload`` field for every pending ``Item*`` entry.

        Converts the accumulated ``statements`` list (raw ``[pid, dtype, value,
        qualifiers]`` tuples) into the Wikibase REST API item-creation format
        and stores it back in the dictionary under ``item_data["payload"]``.
        Must be called after all :meth:`add_answer` / :meth:`add_multiple_relation`
        calls and before posting.
        '''
        for item_id, item_data in self.state.dictionary.items():
            # Check if Item in Payload
            if not item_id.startswith('Item'):
                continue
            # Extract Information
            label = item_data.get("label", "")
            description = item_data.get("description", "")
            aliases = item_data.get("aliases", "")
            statements_input = item_data.get("statements", [])
            # Grouped statements by PID
            statements = {}
            for s in statements_input:
                pid, dtype, obj = s[0], s[1], s[2]
                qualifier = None
                if len(s) == 4:
                    qualifier = s[3]
                statement = {
                    "property": {"id": pid, "data_type": dtype},
                    "value": {"type": "value", "content": obj}
                }
                if qualifier:
                    statement["qualifiers"] = qualifier

                statements.setdefault(pid, []).append(statement)
            # Build payload
            payload = {
                "item": {
                    "labels": {"en": label},
                    "statements": statements
                }
            }
            if description:
                payload["item"]["descriptions"] = {"en": description}
            if aliases:
                payload["item"]["aliases"] = {"en": aliases}
            # Attach to original dict
            item_data["payload"] = payload

    def _statement_by_id_type(self, value: dict, id_type: str):
        """Build the external-identifier statements for a user-defined item.

        Selects which identifier statements to add (Wikidata QID, ORCID iD,
        zbMath ID, or ISSN) based on *id_type* and the fields present in *value*.

        Args:
            value:   Item dict with optional keys ``ID``, ``orcid``, ``zbmath``,
                     and ``issn``.
            id_type: Source of the item (``'wikidata'``), or the kind of a new
                     publication part (``'author'``, ``'journal'``).

        Returns:
            List of ``[property_id, datatype, value_str]`` statement triples.
        """
        statements = []
        if id_type == 'wikidata':
            # Add Wikidata ID
            statements.append(
                [
                    self.wikibase['properties']['Wikidata QID'],
                    'external-id',
                    value['ID'].split(':')[1]
                ]
            )
        if id_type == 'author':
            # Add ORCID ID Statement
            if value.get('orcid'):
                statements.append(
                    [
                        self.wikibase['properties']['ORCID iD'],
                        'external-id',
                        value['orcid']
                    ]
                )
            # Add zbMath ID Statement
            if value.get('zbmath'):
                statements.append(
                    [
                        self.wikibase['properties']['zbMATH author ID'],
                        'external-id',
                        value['zbmath']
                    ]
                )
            # If Authors has ID, add further Statements
            if statements:
                statements += self._marker_statements(value, 'author')
        if id_type == 'journal':
            # Add ISSN ID Statement
            if value.get('issn'):
                statements.append(
                    [
                        self.wikibase['properties']['ISSN'],
                        'external-id',
                        value['issn']
                    ]
                )
            # Add further Statements (as for journals from Wikidata)
            statements += self._marker_statements(value, 'journal')
        return statements

    def _marker_statements(self, value, section):
        """The marker statements of the new author or journal *value* (*section*, see :mod:`MaRDMO.markers`)."""
        self.marked.setdefault(value['ID'], set()).add(section)
        return [[self.wikibase['properties'][MARKER_PROPERTIES[kind]], 'wikibase-item', qid]
                for kind, qid in PUBLICATION_MARKERS[section].qids().items() if qid]

    def process_items(self):
        """Populate the payload dictionary with an entry for every item in ``user_items``.

        Dispatches each item to a source-specific handler based on the prefix
        of its ``ID`` field (``mardi``, ``wikidata``, ``not found`` for the
        user's own items), or for a new author or journal of a publication its
        ``kind`` (``author``, ``journal``, #118).  Existing MaRDI items are
        registered with their real QID; new items get an empty id and a
        seed list of statements.

        Before, the items are looked up on the MaRDI Portal (#141, see
        :meth:`_find_on_portal`); items that exist there stop the export, all
        of them in one :exc:`DocumentationProblem`.
        """
        def new_item(id_type):
            return lambda key, value: self._add_entry(
                key,
                self._build_item(
                    '',
                    value['Name'],
                    # An author or journal named by its identifier (duplicates._resolve_parts)
                    value.get('create_as') or value['Description'],
                    self._statement_by_id_type(value, id_type)
                )
            )

        handlers = {
            'mardi': lambda key, value: self._add_entry(
                key,
                self._build_item(
                    value['ID'].split(':')[1],
                    value['Name'],
                    value['Description'],
                )
            ),
            'wikidata': new_item('wikidata'),
            'not found': new_item('not found'),
            'author': new_item('author'),
            'journal': new_item('journal'),
        }

        todo = []
        for key, value in self.user_items.items():
            id_type = item_source(value)
            if id_type:
                todo.append((id_type, handlers[id_type], key, value))

        self._find_on_portal(todo)
        for id_type, handler, key, value in todo:
            # Authors and journals: left out, or the portal item (duplicates._resolve_parts)
            if value.get('omit'):
                continue
            if value.get('use'):
                self._add_entry(key, self._build_item(value['use'], value['Name'], value['Description']))
            else:
                handler(key, value)
            # Not sent: the export gives these the new item's ID (helpers.replace_ids)
            if value.get('user_ids'):
                self.state.dictionary[key]['user_ids'] = value['user_ids']
            # New authors and journals get all their statements here and are
            # skipped by the publication worker, so their class is set here too
            # (it groups them on the success page)
            if id_type in _NEW_ITEM_CLASS:
                self.state.dictionary[key]['class'] = _NEW_ITEM_CLASS[id_type]

    def _find_on_portal(self, todo):
        """Look up the items of *todo* on the MaRDI Portal before anything is created (#141).

        New and Wikidata items are duplicates if the portal holds an item with
        exactly their label and description (the portal's own rule), Wikidata
        items also if a portal item has their Wikidata QID (P12), see
        :func:`~MaRDMO.duplicates.look_up` (the preview lists the same).  The
        markers of the existing items are kept for :meth:`subject_markers`.

        Raises:
            DocumentationProblem: All duplicates, one line each.
            PortalUnavailable: If the Wikidata QIDs could not be looked up; a
                failed label lookup is only logged (the portal rejects exact
                duplicates itself, and the export links those).
        """
        commit_writes()
        found, duplicates = look_up([(id_type, value) for id_type, _, _, value in todo],
                                    EXPORT_RETRY_WAITS, time.monotonic() + EXPORT_CHECK_DEADLINE)
        if found.wikidata_failed:
            raise PortalUnavailable(
                "Could not check which Wikidata items already exist on the MaRDI Portal "
                "(the portal did not answer). Nothing was exported; please try again later."
            )
        if found.label_failed:
            _logger.warning("Duplicate check by label and description failed; the portal rejects exact duplicates.")
        self.portal_markers = found.markers
        self.markers_known = not found.markers_failed

        messages = []
        for duplicate in duplicates:
            name, description = duplicate.item['Name'], duplicate.item['Description']
            if duplicate.rule == 'documentation':
                messages.append(
                    f"'{name}' ({description}) has the label and description of the Wikidata item "
                    f"{duplicate.other['ID'].split(':', 1)[-1]} of this documentation; the MaRDI Portal takes "
                    "only one item per label and description. Rename yours, or select the Wikidata item."
                )
            elif duplicate.rule == 'wikidata':
                messages.append(
                    f"'{name}' ({description}) is the Wikidata item "
                    f"{duplicate.item['ID'].split(':', 1)[-1]}, which exists on the MaRDI Portal as {duplicate.qid}. "
                    "Use the portal item, or choose another item or make it a new item."
                )
            else:
                messages.append(
                    f"An item ({duplicate.qid}) with the label '{name}' and description "
                    f"'{description}' already exists on the MaRDI Portal. "
                    "Use the portal item, or rename yours."
                )
        if messages:
            raise DocumentationProblem(*messages)
