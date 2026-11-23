'''Wikibase REST API payload builder for MaRDMO exports.

Provides :class:`GeneratePayload`, which transforms a prepared answers dict
into a fully structured payload dict ready for posting to the MaRDI Portal:

- Builds ``Item*`` entries for every unique entity (labels, descriptions,
  aliases, statements, qualifiers).
- Builds ``RELATION_*`` entries for cross-item statements that reference
  other items by their temporary ``Item<n>`` placeholder.
- Builds ``ALIAS_*`` entries for alias additions to existing portal items.

Its parts:

- :mod:`~MaRDMO.payload.bodies`: texts and values cleaned for the portal,
  request bodies and URLs.
- :mod:`~MaRDMO.payload.claims`: the statements against those on the portal.
- :mod:`~MaRDMO.payload.validation`: values the portal would reject.
- :mod:`~MaRDMO.payload.errors`: :exc:`DocumentationProblem`, :exc:`PortalUnavailable`.

Key methods: :meth:`~GeneratePayload.add_data_properties`,
:meth:`~GeneratePayload.add_aliases`,
:meth:`~GeneratePayload.check_existing_relations`.
'''

import logging

from dataclasses import dataclass, field
from typing import Optional

from django.utils.translation import gettext as _

from ..duplicates import item_source, look_up
from ..export.items import item_key
from ..core.markers import MARKER_PROPERTIES, PUBLICATION_MARKERS
from ..ordering import cycle_groups
from ..sources.http import check_deadline, check_waits
from ..project.writes import commit_writes
from . import claims
from .bodies import (
    ITEM_KEY_RE,
    TEXT_TYPES,
    alias_url,
    build_alias,
    build_item,
    build_qualifier,
    build_statement,
    normalize_aliases,
    statement_url,
    strip_text,
    text_of,
)
from .errors import DocumentationProblem, PortalUnavailable
from .validation import dangling_references, invalid_values

__all__ = ['DocumentationProblem', 'GeneratePayload', 'PayloadState', 'PortalUnavailable']

_logger = logging.getLogger(__name__)


# Class of new authors and journals of publications (kind, see ids.PART_KINDS)
_NEW_ITEM_CLASS = {'author': 'Author', 'journal': 'Journal'}


def _item_references(statement):
    '''The ``Item<n>`` keys a statement ``[pid, type, value, qualifiers]`` of a new item refers to.'''
    found = set()
    values = [statement[2]] + [qualifier['value']['content'] for qualifier in
                               (statement[3] if len(statement) > 3 else [])]
    for value in values:
        if isinstance(value, str) and ITEM_KEY_RE.match(value):
            found.add(value)
    return found


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
                         :func:`~MaRDMO.export.items.unique_items`.
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
            DocumentationProblem: If *value* is empty, or an item the export
                creates misses ``Name``/``Description`` (a MaRDI Portal item
                is found by its ID, it may lack them, #167).
        """
        if not value:
            raise DocumentationProblem(_("Missing Item in Statement!"))
        on_portal = str(value.get('ID') or '').startswith('mardi:')
        if not on_portal and (not value.get('Name') or not value.get('Description')):
            raise DocumentationProblem(_("All Items need to have a 'Name' and 'Description'!"))

        item_key = self._find_key_by_values(
            value['ID'],
            value.get('Name') or '',
            value.get('Description') or '',
        )

        if role == 'subject':
            self.state.subject = value
            self.state.subject_item = item_key

        return item_key

    def set_class(self, name: str) -> None:
        '''Tag the current subject item with an entity-class label.

        Used by ``_export_*`` worker methods so that :func:`~MaRDMO.export.items.compare_items`
        can include the class in its output for grouping on the success page.

        Args:
            name: Human-readable class label (e.g. ``'Mathematical Model'``).
        '''
        if self.state.subject_item:
            self.state.dictionary[self.state.subject_item]['class'] = name

    def add_qualifier(self, identifier, data_type, content):
        '''Build a single-qualifier list for use in :meth:`add_answer` (:func:`~MaRDMO.payload.bodies.build_qualifier`).'''
        return build_qualifier(identifier, data_type, content)

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

    def final_checks(self, api_url):
        '''Check the finished payload against the portal's rules and the portal itself.

        Runs :meth:`check_existing_relations` and :meth:`validate_identifiers`
        and reports the problems of both at once (#152), so the preview lists
        all of them, not only those of the first check.  The existence check
        comes first: values of statements that are on the portal already are
        not written, so they are not validated (#167).

        Raises:
            DocumentationProblem: Every invalid value and every symbol that
                stands for another quantity on the portal, one argument each.
            PortalUnavailable: If the portal does not answer.
            ValueError: A placeholder without item (an internal error).
        '''
        problems = []
        try:
            self.check_existing_relations(api_url)
        except DocumentationProblem as problem:
            problems += problem.args
        try:
            self.validate_identifiers()
        except DocumentationProblem as problem:
            problems += problem.args
        if problems:
            raise DocumentationProblem(*problems)

    def validate_identifiers(self):
        '''Reject malformed URLs, DOIs, swMATH IDs, dates and amounts before anything is posted.

        Applies the strict rules from :mod:`~MaRDMO.validators` to every URL
        statement and qualifier and to every "DOI" and "swMath work ID" value,
        checks that every time value is a ``+YYYY-MM-DDThh:mm:ssZ`` string and
        every quantity amount a Wikibase decimal (``+8``, ``+1.5``).
        This catches values that bypassed the pre-save validator, the preview
        and the checks, so an export never fails halfway because of them.
        Only what is written: statements the portal has already
        (:meth:`check_existing_relations` marked them) are left out (#167);
        see :func:`~MaRDMO.payload.validation.invalid_values`.

        Raises:
            DocumentationProblem: One argument per invalid value, naming item and property.
            ValueError: One argument per placeholder without item (an internal error).
        '''
        errors = invalid_values(self.state.dictionary, self.wikibase['properties'])
        if errors:
            raise DocumentationProblem(*errors)
        dangling = dangling_references(self.state.dictionary)
        if dangling:
            # an internal error, not the user's: a plain ValueError
            raise ValueError(*dangling)

    def check_existing_relations(self, api_url):
        '''Mark every RELATION entry that already exists on the portal.

        Fetches the claims of the existing items the RELATION entries belong
        to (wbgetentities, 50 items per request) and decides each entry with
        :func:`~MaRDMO.payload.claims.exists_in_claims`.  The qualifier merge
        and the symbol check use the same claims.  Failed requests are retried after
        :data:`~MaRDMO.sources.http.EXPORT_RETRY_WAITS`; all of them together give
        up after :data:`~MaRDMO.sources.http.EXPORT_CHECK_DEADLINE` seconds (in the
        preview its shorter limits, :func:`~MaRDMO.sources.http.check_limits`).

        Args:
            api_url: Action API URL of the portal.

        Raises:
            PortalUnavailable: If the claims cannot be fetched.  Posting without
                the check would duplicate statements on existing items.
        '''
        relations = {key: entry for key, entry in self.state.dictionary.items() if key.startswith('RELATION')}
        if not relations:
            return

        deadline = check_deadline()
        subjects = {claims.resolve_item_reference(self.state.dictionary, entry['url'].split('/')[-2])
                    for entry in relations.values()}
        found = self._fetch_claims(
            sorted(s for s in subjects if isinstance(s, str) and claims.QID_RE.match(s)), api_url, deadline,
            'statements',
        )
        for entry in relations.values():
            entry['exists'] = claims.exists_in_claims(self.state.dictionary, entry, found)

        # Statements that only add qualifiers (e.g. another assumption) extend
        # the portal statement instead of duplicating it
        self.merge_qualifiers(api_url, deadline)
        # Symbols of formulas: complete a symbol without quantity, stop if it
        # stands for another quantity
        self.check_symbols(api_url, deadline)

    def _fetch_claims(self, qids, api_url, deadline, what):
        '''Return ``{qid: claims}`` of portal items (:func:`~MaRDMO.payload.claims.fetch_claims`).

        Items fetched before during this export are taken from the earlier
        answer (the existence check, the qualifier merge and the symbol check need the same).
        '''
        return claims.fetch_claims(qids, api_url, deadline, what, self._claims)

    def merge_qualifiers(self, api_url, deadline=None):
        '''Turn new statements that only add qualifiers into additions to the portal statement.

        See :func:`~MaRDMO.payload.claims.merge_qualifiers`.
        '''
        claims.merge_qualifiers(self.state.dictionary, self.wikibase['properties'],
                                lambda qids: self._fetch_claims(qids, api_url, deadline, 'statements'))

    def check_symbols(self, api_url, deadline=None):
        '''Compare new "in defining formula" statements with the symbols of the item on the portal.

        See :func:`~MaRDMO.payload.claims.check_symbols`.
        '''
        claims.check_symbols(self.state.dictionary, self.wikibase['properties'],
                             lambda qids: self._fetch_claims(qids, api_url, deadline, 'formulas'))

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
        aliases_list = normalize_aliases(aliases_dict)
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
        value = strip_text(object_and_type[0], object_and_type[1])
        if object_and_type[1] in TEXT_TYPES and not text_of(value):
            return
        # Gather Statement
        statement = {
            'property_id': verb,
            'datatype': object_and_type[1],
            'value': value
        }
        # Statements of existing items are added to them; those of new
        # items are created with them (the dependencies: order_items)
        if self.state.dictionary[subject]['id']:
            self._add_relation(
                item=subject,
                statement=statement,
                qualifier=qualifier
            )
        else:
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
            # A symbol without quantity adds nothing to a new item.  A
            # quantity whose formula has its own symbol refers to itself:
            # order_items adds that statement after its creation (#164)
            if self.state.dictionary[self.state.subject_item]['id'] or ITEM_KEY_RE.match(quantity_item or ''):
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
            'url': statement_url(self.url, item),
            'payload': build_statement(
                statement['property_id'],
                strip_text(statement['value'], statement['datatype']),
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
                'url': alias_url(self.url, item),
                'payload': build_alias(
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
        calls and before posting.  First :meth:`order_items` builds the order
        of creation.
        '''
        self.order_items()
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

    def order_items(self):
        '''Build the dependencies of the new items and break their cycles (#164).

        A new item is created with its statements, after every item they
        refer to, in the value or in a qualifier (e.g. the formula an
        assumption names, the software of an algorithm in a process step).
        ``self.dependency`` becomes these references.  Items that refer to
        each other in a cycle cannot be ordered: of each cycle, the item with
        the fewest statements to the other items of the cycle (ties: the
        lower key) gets these statements afterwards, as single statements
        on the created item (``RELATION`` entries, qualifiers included),
        until no cycle is left.  A statement of an item about itself is added
        afterwards too.  A documentation without cycles keeps all its
        statements in its items.
        '''
        dictionary = self.state.dictionary
        keys = {key for key in dictionary if key.startswith('Item')}
        new = {key for key in keys if not dictionary[key].get('id')}
        references = {key: [_item_references(statement) & keys for statement in dictionary[key].get('statements', [])]
                      for key in sorted(new)}

        def postpone(key, closing):
            '''Move the statements of *key* that refer to an item of *closing* into RELATION entries.'''
            kept, kept_references = [], []
            for statement, refs in zip(dictionary[key]['statements'], references[key]):
                if refs & closing:
                    self._add_relation(
                        item=key,
                        statement={'property_id': statement[0], 'datatype': statement[1], 'value': statement[2]},
                        qualifier=statement[3] if len(statement) > 3 else [])
                else:
                    kept.append(statement)
                    kept_references.append(refs)
            dictionary[key]['statements'], references[key] = kept, kept_references

        def graph():
            return {key: set().union(*references[key]) - {key} if key in references else set()
                    for key in sorted(keys)}

        for key in references:
            if any(key in refs for refs in references[key]):
                postpone(key, {key})
        # Each cycle is broken within itself: what is left of it may form smaller cycles
        groups = cycle_groups({key: set().union(*references[key]) & new for key in references})
        while groups:
            members = set(groups.pop())
            chosen = min(sorted(members), key=lambda key: (sum(bool(refs & members) for refs in references[key]), key))
            postpone(chosen, members - {chosen})
            # The chosen item refers to no other item of the cycle any more
            rest = members - {chosen}
            groups += cycle_groups({key: set().union(*references[key]) & rest for key in rest})
        self.dependency.clear()
        self.dependency.update(graph())

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
        """The marker statements of the new author or journal *value* (*section*, see :mod:`MaRDMO.core.markers`)."""
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
                build_item(
                    self.url,
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
                build_item(
                    self.url,
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
                self._add_entry(key, build_item(self.url, value['use'], value['Name'], value['Description']))
            else:
                handler(key, value)
            # Not sent: the export gives these the new item's ID (ids.replace_ids)
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
        items also if a portal item has their Wikidata QID (P12), publications
        also if one has their DOI (#158), see
        :func:`~MaRDMO.duplicates.look_up` (the preview lists the same).  The
        markers of the existing items are kept for :meth:`subject_markers`.

        Raises:
            DocumentationProblem: All duplicates, one line each.
            PortalUnavailable: If the Wikidata QIDs or DOIs could not be looked up; a
                failed label lookup is only logged (the portal rejects exact
                duplicates itself, and the export links those).
        """
        commit_writes()
        found, duplicates = look_up([(id_type, value) for id_type, _, _, value in todo],
                                    check_waits(), check_deadline())
        if found.wikidata_failed:
            raise PortalUnavailable(_(
                "Could not check which Wikidata items already exist on the MaRDI Portal "
                "(the portal did not answer). Nothing was exported; please try again later."
            ))
        if found.doi_failed:
            raise PortalUnavailable(_(
                "Could not check which publications already exist on the MaRDI Portal by their DOI "
                "(the portal did not answer). Nothing was exported; please try again later."
            ))
        if found.label_failed:
            _logger.warning("Duplicate check by label and description failed; the portal rejects exact duplicates.")
        self.portal_markers = found.markers
        self.markers_known = not found.markers_failed

        messages = []
        for duplicate in duplicates:
            name, description = duplicate.item['Name'], duplicate.item['Description']
            if duplicate.rule == 'documentation':
                messages.append(_(
                    "'{name}' ({description}) has the label and description of the Wikidata item {qid} of this "
                    "documentation; the MaRDI Portal takes only one item per label and description. Rename yours, "
                    "or select the Wikidata item."
                ).format(name=name, description=description, qid=duplicate.other['ID'].split(':', 1)[-1]))
            elif duplicate.rule == 'doi':
                messages.append(_(
                    "'{name}' has the DOI {doi}, which the MaRDI Portal has as {portal_qid}: it is this "
                    "publication. Use the portal item (in the preview), or correct the DOI."
                ).format(name=name or f"doi:{duplicate.item['doi']}", doi=duplicate.item['doi'],
                         portal_qid=duplicate.qid))
            elif duplicate.rule == 'wikidata':
                messages.append(_(
                    "'{name}' ({description}) is the Wikidata item {qid}, which exists on the MaRDI Portal as "
                    "{portal_qid}. Use the portal item, or choose another item or make it a new item."
                ).format(name=name, description=description, qid=duplicate.item['ID'].split(':', 1)[-1],
                         portal_qid=duplicate.qid))
            else:
                messages.append(_(
                    "An item ({qid}) with the label '{name}' and description '{description}' already exists on "
                    "the MaRDI Portal. Use the portal item, or rename yours."
                ).format(qid=duplicate.qid, name=name, description=description))
        if messages:
            raise DocumentationProblem(*messages)
