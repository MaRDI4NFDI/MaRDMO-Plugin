'''Wikibase REST API payload builder for MaRDMO exports.

Provides :class:`GeneratePayload`, which transforms a prepared answers dict
into a fully structured payload dict ready for posting to the MaRDI Portal:

- Builds ``Item*`` entries for every unique entity (labels, descriptions,
  aliases, statements, qualifiers).
- Builds ``RELATION_*`` entries for cross-item statements that reference
  other items by their temporary ``Item<n>`` placeholder.
- Builds ``ALIAS_*`` entries for alias additions to existing portal items.

Key methods: :meth:`~GeneratePayload.add_data_properties`,
:meth:`~GeneratePayload.add_check_results`,
:meth:`~GeneratePayload.add_aliases`,
:meth:`~GeneratePayload.build_relation_check_query`.
'''

import logging

from dataclasses import dataclass, field
from typing import Optional

import re
import time
import requests

from .queries import query_item, query_sparql, sparql_string
from .validators import REPOSITORY_URL_SCHEMES, WEB_URL_SCHEMES, doi_problem, swmath_problem, url_problem

_logger = logging.getLogger(__name__)

# Datatypes whose values the portal stores as single-line text
_TEXT_TYPES = ('string', 'external-id', 'url', 'URL', 'monolingualtext')

_XSD = 'http://www.w3.org/2001/XMLSchema#'
# How the query service stores the unit of unitless quantities (unit "1")
_UNITLESS_IRI = 'http://www.wikidata.org/entity/Q199'
_QID_RE = re.compile(r'^Q\d+$')
_LANG_TAG_RE = re.compile(r'^[a-zA-Z]+(-[a-zA-Z0-9]+)*$')
_IRI_INVALID_RE = re.compile(r'[\x00-\x20<>"{}|^`\\]')
_TIME_RE = re.compile(r'^\+?(-?\d+)-(\d{2})-(\d{2})(T.*)$')
# Invisible whitespace the portal rejects; replaced by spaces on export
_INVISIBLE_WHITESPACE_RE = re.compile(r'[\t\v\f]')

# Relations per existence-check query; keeps single queries small and fast
_RELATION_CHECK_CHUNK = 50
# Pauses (seconds) before retrying a failed existence-check query
_RELATION_CHECK_RETRY_DELAYS = (2, 5)


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
    '''Apply :func:`_clean_text` to text values.

    Values of non-text datatypes are returned unchanged.
    '''
    if data_type not in _TEXT_TYPES:
        return value
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict) and isinstance(value.get('text'), str):
        return {**value, 'text': _clean_text(value['text'])}
    return value


def _normalize_time(value):
    '''Convert a Wikibase time string to the form stored by the query service.

    The query service drops the leading ``+`` and turns month/day ``00`` into
    ``01`` (``+2020-00-00T00:00:00Z`` → ``2020-01-01T00:00:00Z``).  Returns
    ``None`` if *value* is not a recognisable time string.
    '''
    match = _TIME_RE.match(str(value))
    if not match:
        return None
    year, month, day, rest = match.groups()
    return f"{year}-{month if month != '00' else '01'}-{day if day != '00' else '01'}{rest}"

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

    def build_relation_check_queries(self):
        '''Build SPARQL queries that check which RELATION entries already exist.

        Each relation becomes one ``BIND(EXISTS {…} AS ?RELATION<n>)`` clause,
        so every query returns exactly one row of booleans regardless of how
        many matching statements the portal holds.  Relations are split into
        chunks of :data:`_RELATION_CHECK_CHUNK` to keep queries small.
        Relations that cannot be expressed in SPARQL (see
        :meth:`_build_relation_block`) are left out and count as new.

        Returns:
            List of SPARQL query strings (empty when nothing can be checked).
        '''
        relation_keys = [k for k in self.state.dictionary if k.startswith('RELATION')]
        blocks = []
        for idx, key in enumerate(relation_keys):
            block = self._build_relation_block(idx, self.state.dictionary[key])
            if block is not None:
                blocks.append((idx, block))

        queries = []
        for start in range(0, len(blocks), _RELATION_CHECK_CHUNK):
            chunk = blocks[start:start + _RELATION_CHECK_CHUNK]
            selectors = ' '.join(f'?RELATION{idx}' for idx, _ in chunk)
            body = '\n'.join(block for _, block in chunk)
            queries.append(f'SELECT {selectors} WHERE {{\n{body}\n}}')
        return queries

    def _sparql_value(self, value, data_type):
        '''Format a simple statement value as a SPARQL term.

        Args:
            value:     Raw value (string, QID, or monolingual-text dict).
            data_type: Wikibase datatype string.

        Returns:
            SPARQL term string, or ``None`` when the value cannot be matched
            reliably via SPARQL (math, invalid IRIs, unknown structures).
        '''
        if data_type == 'wikibase-item':
            if isinstance(value, str) and _QID_RE.match(value):
                return f'wd:{value}'
            return None
        if data_type == 'math':
            # The query service returns math as MathML; checked via the API instead
            return None
        if data_type in ('url', 'URL'):
            if isinstance(value, str) and value and not _IRI_INVALID_RE.search(value):
                return f'<{value}>'
            return None
        if data_type == 'monolingualtext':
            if isinstance(value, dict):
                text, language = value.get('text'), value.get('language', 'en')
            else:
                text, language = value, 'en'
            if text and _LANG_TAG_RE.match(str(language)):
                return f'{sparql_string(text)}@{language}'
            return None
        if value is None or isinstance(value, (dict, list)):
            return None
        return sparql_string(value)

    def _value_node_triples(self, statement_var, predicate, node_var, value, data_type):
        '''Build triples matching a quantity or time value node.

        Args:
            statement_var: SPARQL variable of the statement (e.g. ``?statement3``).
            predicate:     Value-node predicate (``psv:P1`` or ``pqv:P2``).
            node_var:      SPARQL variable for the value node.
            value:         Value dict with ``amount`` or ``time``.
            data_type:     ``"quantity"`` or ``"time"``.

        Returns:
            Triple-pattern string, or ``None`` for unsupported values.
        '''
        if data_type == 'quantity' and value.get('amount'):
            literal = f'{sparql_string(value["amount"])}^^<{_XSD}decimal>'
            unit = str(value.get('unit', '1'))
            if unit == '1':
                unit_triples = f'  {node_var} wikibase:quantityUnit <{_UNITLESS_IRI}> .\n'
            else:
                # Compare the unit by QID: the portal stores whatever entity
                # URI was posted (http/https, internal host names)
                unit_qid = unit.rsplit('/', 1)[-1]
                if not _QID_RE.match(unit_qid):
                    return None
                unit_triples = (
                    f'  {node_var} wikibase:quantityUnit {node_var}_unit .\n'
                    f'  FILTER(STRENDS(STR({node_var}_unit), "/entity/{unit_qid}"))\n'
                )
            return (
                f'  {statement_var} {predicate} {node_var} .\n'
                f'  {node_var} wikibase:quantityAmount {literal} .\n'
                f'{unit_triples}'
            )
        if data_type == 'time':
            time_str = _normalize_time(value.get('time', ''))
            if time_str:
                literal = f'{sparql_string(time_str)}^^<{_XSD}dateTime>'
                return (
                    f'  {statement_var} {predicate} {node_var} .\n'
                    f'  {node_var} wikibase:timeValue {literal} .\n'
                )
        return None

    def _resolve_item_reference(self, value):
        '''Replace an ``Item<n>`` placeholder by its QID.

        Returns the QID, *value* unchanged when it is not a placeholder, or
        ``''`` when the placeholder refers to an item that does not exist yet.
        '''
        if isinstance(value, str) and value in self.state.dictionary:
            return self.state.dictionary[value].get('id', '')
        return value

    def _build_qualifier_triples(self, qualifiers, idx):
        '''Build SPARQL triple patterns for a list of qualifier dicts.

        Args:
            qualifiers: List of qualifier dicts (each with ``property`` and
                        ``value`` sub-dicts).
            idx:        Statement index used to name the ``?statement<idx>``
                        SPARQL variable.

        Returns:
            SPARQL triple-pattern string (empty when *qualifiers* is empty), or
            ``None`` when a qualifier cannot be matched — either it refers to a
            not-yet-created item (so the statement cannot exist yet) or its
            value cannot be expressed in SPARQL.
        '''
        triples = ''
        for q_idx, q in enumerate(qualifiers):
            q_prop = q['property']['id']
            q_data_type = q['property']['data_type']
            q_value = self._resolve_item_reference(q['value']['content'])
            if q_value == '':
                return None
            if isinstance(q_value, dict) and q_data_type in ('quantity', 'time'):
                value_triples = self._value_node_triples(
                    f'?statement{idx}', f'pqv:{q_prop}', f'?qval{idx}_{q_idx}',
                    q_value, q_data_type,
                )
                if value_triples is None:
                    return None
                triples += value_triples
            else:
                value_str = self._sparql_value(q_value, q_data_type)
                if value_str is None:
                    return None
                triples += f'  ?statement{idx} pq:{q_prop} {value_str} .\n'
        return triples

    def _build_relation_block(self, idx, entry):
        '''Build the ``BIND(EXISTS …)`` clause for one RELATION entry.

        Args:
            idx:   Relation index used to name SPARQL variables.
            entry: RELATION payload dict from ``self.state.dictionary``.

        Returns:
            SPARQL clause string, or ``None`` when the relation cannot be
            checked via SPARQL (target item not on the portal yet, value or
            qualifier not expressible, math values).
        '''
        target_item_key = entry['url'].split('/')[-2]
        target_item_id = self._resolve_item_reference(target_item_key)
        if not (isinstance(target_item_id, str) and _QID_RE.match(target_item_id)):
            return None

        statement = entry['payload']['statement']
        prop_id = statement['property']['id']
        data_type = statement['property']['data_type']
        value = self._resolve_item_reference(statement['value']['content'])
        if value == '':
            return None

        if isinstance(value, dict) and data_type in ('quantity', 'time'):
            value_triples = self._value_node_triples(
                f'?statement{idx}', f'psv:{prop_id}', f'?sval{idx}', value, data_type,
            )
        else:
            value_str = self._sparql_value(value, data_type)
            value_triples = (
                f'  ?statement{idx} ps:{prop_id} {value_str} .\n'
                if value_str is not None else None
            )
        if value_triples is None:
            return None

        qual_triples = self._build_qualifier_triples(statement.get('qualifiers', []), idx)
        if qual_triples is None:
            return None

        return (
            f'BIND(EXISTS {{\n'
            f'  wd:{target_item_id} p:{prop_id} ?statement{idx} .\n'
            f'{value_triples}'
            f'{qual_triples}'
            f'}} AS ?RELATION{idx})'
        )

    def _find_key_by_values(self, id_value, name_value, description_value):
        '''Look up the ``"Item<n>"`` key matching the given ID, Name, and Description.

        Args:
            id_value:          ``ID`` field value to match.
            name_value:        ``Name`` field value to match.
            description_value: ``Description`` field value to match.

        Returns:
            Matching ``"Item<n>"`` key string, or ``None`` if not found.
        '''
        for key, values in self.user_items.items():
            if (values['ID'] == id_value and
                values['Name'] == name_value and
                values['Description'] == description_value):
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
            ValueError: If *value* is empty or missing ``Name``/``Description``.
        """
        if not value:
            raise ValueError("Missing Item in Statement!")
        if not value.get('Name') or not value.get('Description'):
            raise ValueError("All Items need to have a 'Name' and 'Description'!")

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

    def add_check_results(self, check):
        '''Update each RELATION entry with its existence check result.

        Args:
            check: Dict mapping ``"RELATION<n>"`` to ``'true'``/``'false'``;
                   relations missing from *check* are treated as new.
        '''
        relation_keys = [k for k in self.state.dictionary if k.startswith('RELATION')]
        for idx, key in enumerate(relation_keys):
            self.state.dictionary[key]['exists'] = check.get(f'RELATION{idx}', 'false')

    def validate_identifiers(self):
        '''Reject malformed URLs, DOIs, swMATH IDs and dates before anything is posted.

        Applies the strict rules from :mod:`~MaRDMO.validators` to every URL
        statement and qualifier and to every "DOI" and "swMath work ID" value,
        and checks that every time value is a ``+YYYY-MM-DDThh:mm:ssZ`` string.
        This catches values that bypassed the pre-save validator, the preview
        and the checks, so an export never fails halfway because of them.

        Raises:
            ValueError: One argument per invalid value, naming item and property.
        '''
        properties = self.wikibase['properties']
        pid_to_name = {pid: name for name, pid in properties.items()}
        repository_pid = properties.get('source code repository URL')
        doi_pid = properties.get('DOI')
        swmath_pid = properties.get('swMath work ID')
        errors = []

        def check(item_name, prop_id, data_type, value):
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
            return data_type in ('url', 'URL', 'time') or prop_id in (doi_pid, swmath_pid)

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
            raise ValueError(*errors)

    def check_existing_relations(self, sparql_endpoint, api_url):
        '''Mark every RELATION entry that already exists on the portal.

        Runs the SPARQL existence checks from :meth:`build_relation_check_queries`
        (retrying failed queries) and checks math statements via the API.

        Args:
            sparql_endpoint: SPARQL endpoint URL of the portal.
            api_url:         Action API URL of the portal (for math statements).

        Raises:
            ValueError: If a check cannot be completed.  Posting without the
                check would duplicate statements on existing items.
        '''
        if not any(key.startswith('RELATION') for key in self.state.dictionary):
            return

        check = {}
        for query in self.build_relation_check_queries():
            bindings = query_sparql(query, sparql_endpoint)
            for delay in _RELATION_CHECK_RETRY_DELAYS:
                if bindings:
                    break
                _logger.warning("Relation check query failed, retrying in %s s", delay)
                time.sleep(delay)
                bindings = query_sparql(query, sparql_endpoint)
            # A successful query always returns exactly one row
            if not bindings:
                raise ValueError(
                    "Could not check which statements already exist on the MaRDI Portal "
                    "(query service not reachable or query rejected). "
                    "Nothing was exported; please try again later."
                )
            check.update({
                key: binding.get('value', 'false')
                for key, binding in bindings[0].items()
            })

        # SPARQL returns math values as MathML; check math statements via API.
        # Its results are keyed by dictionary key, the SPARQL results by index.
        relation_index = {
            key: idx for idx, key in enumerate(
                k for k in self.state.dictionary if k.startswith('RELATION')
            )
        }
        for key, exists in self.check_math_relations_via_api(api_url).items():
            check[f'RELATION{relation_index[key]}'] = exists

        self.add_check_results(check)

    def check_math_relations_via_api(self, api_url):
        '''Check existence of math-datatype RELATION statements via wbgetentities.

        SPARQL returns math values as MathML, but portal stores LaTeX.  This
        method queries the Wikibase API directly to compare raw LaTeX values.

        Returns {relation_key: 'true'/'false'}.

        Raises:
            ValueError: If the claims of an existing item cannot be fetched.
        '''
        relation_keys = [k for k in self.state.dictionary if k.startswith('RELATION')]
        math_entries  = {}  # key → (item_qid, prop_id, latex, qualifiers)

        for key in relation_keys:
            entry     = self.state.dictionary[key]
            statement = entry['payload']['statement']
            if statement['property']['data_type'] != 'math':
                continue
            item_qid = self._resolve_item_reference(entry['url'].split('/')[-2])
            if not item_qid:
                continue  # new item → statement cannot exist yet
            math_entries[key] = (
                item_qid,
                statement['property']['id'],
                statement['value']['content'],
                statement.get('qualifiers', []),
            )

        if not math_entries:
            return {}

        # Fetch claims for all relevant items
        items_needed   = set(v[0] for v in math_entries.values())
        claims_by_item = {}
        chunk_size     = 50

        items_needed = sorted(items_needed)
        for i in range(0, len(items_needed), chunk_size):
            chunk = items_needed[i:i + chunk_size]
            body = None
            for delay in (0,) + _RELATION_CHECK_RETRY_DELAYS:
                time.sleep(delay)
                try:
                    resp = requests.get(
                        api_url,
                        params={
                            'action': 'wbgetentities',
                            'ids':    '|'.join(chunk),
                            'props':  'claims',
                            'format': 'json',
                        },
                        headers={'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    body = resp.json()
                except (requests.exceptions.RequestException, ValueError) as exc:
                    _logger.warning("Math relation API check failed: %s", exc)
                    continue
                if 'error' in body:
                    _logger.warning("Math relation API check failed: %s", body['error'])
                    body = None
                    continue
                break
            if body is None:
                raise ValueError(
                    "Could not check which formulas already exist on the MaRDI Portal "
                    "(API not reachable). Nothing was exported; please try again later."
                )
            for qid, entity in body.get('entities', {}).items():
                claims_by_item[qid] = entity.get('claims', {})

        result = {}
        for key, (item_qid, prop_id, latex, qualifiers) in math_entries.items():
            exists = 'false'
            for claim in claims_by_item.get(item_qid, {}).get(prop_id, []):
                claim_val = claim.get('mainsnak', {}).get('datavalue', {}).get('value', '')
                if claim_val != latex:
                    continue
                if not qualifiers:
                    exists = 'true'
                    break
                # Check that all qualifiers match
                qual_match = True
                for q in qualifiers:
                    q_prop = q['property']['id']
                    q_val  = self._resolve_item_reference(q['value']['content'])
                    api_qual_vals = []
                    for c in claim.get('qualifiers', {}).get(q_prop, []):
                        api_val = c.get('datavalue', {}).get('value')
                        if isinstance(api_val, dict) and 'id' in api_val:
                            api_val = api_val['id']
                        api_qual_vals.append(api_val)
                    if not q_val or q_val not in api_qual_vals:
                        qual_match = False
                        break
                if qual_match:
                    exists = 'true'
                    break
            result[key] = exists

        return result

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
        *alt_statement* with a string value.

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
            else:
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
        ``subject[statement["relatant"]]`` simultaneously, attaching optional
        series-ordinal, assumption, and object-role qualifiers as configured
        by *optional_qualifier*.

        Args:
            statement:          Dict with ``relation`` and ``relatant`` keys.
            optional_qualifier: List of qualifier type strings to attach; supported
                                values are ``"series ordinal"``, ``"assumes"``.
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

                # Add Formulation and Task Order Numbers to Qualifier
                if 'series ordinal' in optional_qualifier:
                    for number in ('formulation_number', 'task_number'):
                        if self.state.subject.get(number, {}).get(key, {}):
                            qualifier = self.add_qualifier(
                                self.wikibase['properties']['series ordinal'],
                                'string', 
                                self.state.subject[number][key]
                            )

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
                statement['value'],
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

    def _check_mardi_and_raise(self, name: str, description: str):
        """Check if item exists in MaRDI Portal and raise error if it does."""
        mardi_identifier = query_item(name, description)
        if mardi_identifier:
            raise ValueError(
                f"An item ({mardi_identifier}) with the label '{name}' "
                f"and description '{description}' already exists on the MaRDI Portal. "
                "If you intend to use this item, please select it in the questionnaire. "
                "Otherwise, redefine it."
            )
        return mardi_identifier

    def _statement_by_id_type(self, value: dict, id_type: str):
        """Build the external-identifier statements for a user-defined item.

        Selects which identifier statements to add (Wikidata QID, ORCID iD,
        zbMath ID, or ISSN) based on *id_type* and the fields present in *value*.

        Args:
            value:   Item dict with optional keys ``ID``, ``orcid``, ``zbmath``,
                     and ``issn``.
            id_type: Source tag string (e.g. ``'wikidata'``,
                     ``'no author found'``, ``'no journal found'``).

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
        if id_type == 'no author found':
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
                statements.append(
                    [
                        self.wikibase['properties']['instance of'],
                        'wikibase-item',
                        self.wikibase['items']['human']
                    ]
                )
                statements.append(
                    [
                        self.wikibase['properties']['MaRDI profile type'],
                        'wikibase-item',
                        self.wikibase['items']['MaRDI person profile']
                    ]
                )
        if id_type == 'no journal found':
            # Add ISSN ID Statement
            if value.get('issn'):
                statements.append(
                    [
                        self.wikibase['properties']['ISSN'],
                        'external-id',
                        value['issn']
                    ]
                )
            # Add further Statements
            statements.append(
                [
                    self.wikibase['properties']['instance of'],
                    'wikibase-item',
                    self.wikibase['items']['scientific journal']
                ]
            )
        return statements

    def process_items(self):
        """Populate the payload dictionary with an entry for every item in ``user_items``.

        Dispatches each item to a source-specific handler based on the prefix
        of its ``ID`` field (``mardi``, ``wikidata``, ``not found``,
        ``no author found``, ``no journal found``).  Existing MaRDI items are
        registered with their real QID; new items get an empty id and a
        seed list of statements.  Raises :exc:`ValueError` for Wikidata or
        user-created items whose label/description combination already exists
        on the MaRDI Portal.
        """
        handlers = {
            'mardi': lambda key, value: 
                self._add_entry(
                    key,
                    self._build_item(
                        value['ID'].split(':')[1],
                        value['Name'],
                        value['Description'],
                    )
                ),
            'wikidata': lambda key, value: (
                self._check_mardi_and_raise(
                    value['Name'],
                    value['Description']
                ),
                self._add_entry(
                    key,
                    self._build_item(
                        '',
                        value['Name'],
                        value['Description'],
                        self._statement_by_id_type(
                            value,
                            'wikidata'))
                )
            ),
            'not found': lambda key, value: (
                self._check_mardi_and_raise(
                    value['Name'],
                    value['Description']
                ),
                self._add_entry(
                    key,
                    self._build_item(
                        '',
                        value['Name'],
                        value['Description'],
                        self._statement_by_id_type(
                            value,
                            'not found'
                        )
                    )
                )
            ),
            'no author found': lambda key, value: (
                self._check_mardi_and_raise(
                    value['Name'],
                    value['Description']
                ),
                self._add_entry(
                    key,
                    self._build_item(
                        '',
                        value['Name'],
                        value['Description'],
                        self._statement_by_id_type(
                            value,
                            'no author found'
                        )
                    )
                )
            ),
            'no journal found': lambda key, value: (
                self._check_mardi_and_raise(
                    value['Name'],
                    value['Description']
                ),
                self._add_entry(
                    key,
                    self._build_item(
                        '',
                        value['Name'],
                        value['Description'],
                        self._statement_by_id_type(
                            value,
                            'no journal found'
                        )
                    )
                )
            ),
        }

        for key, value in self.user_items.items():
            if not value.get('ID'):
                continue
            for id_type, handler in handlers.items():
                if id_type in value['ID']:
                    if id_type == 'no author found':
                        if value['zbmath'] or value['orcid']:
                            handler(key, value)
                    else:
                        handler(key, value)
                    break
