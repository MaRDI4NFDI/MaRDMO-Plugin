'''General-purpose helper functions and utilities shared across all MaRDMO modules.

Contains:

- :class:`PropertyRegistry` — O(1) lookup for ontology properties by key, label, or URL.
- Answer-routing utilities: :func:`extract_parts`, :func:`basic_dict`,
  :func:`basic_list`, :func:`split_value`, :func:`nested_set`.
- Questionnaire write helpers: :func:`value_editor`.
- Graph utilities: :func:`topological_order`, :func:`is_cyclic`.
- Date helpers: :func:`date_format`, :func:`date_precision`.
- Entity-relation processing: :func:`entity_relations`,
  :func:`entity_relations_grouped`, :func:`map_entity`,
  :func:`build_new_value`, :func:`resolve_target`, :func:`label_index_map`.
- Export helpers: :func:`unique_items`, :func:`compare_items`,
  :func:`replace_in_dict`.
- Questionnaire utilities: :func:`process_question_dict`,
  :func:`define_setup`, :func:`rank_by_search_term`.
'''

import re

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Optional, Any
from collections import defaultdict, deque

from rdmo.projects.models import Value
from rdmo.domain.models import Attribute
from rdmo.options.models import Option

# Set while MaRDMO itself writes values (hydration, publication lookup, ID
# write-back); the pre-save router skips validators then, since they are meant
# for user input and imported data is checked by preview, checks and export
_INTERNAL_WRITE = ContextVar('mardmo_internal_write', default=False)


@contextmanager
def internal_write():
    '''Mark the values saved inside this block as written by MaRDMO itself.'''
    token = _INTERNAL_WRITE.set(True)
    try:
        yield
    finally:
        _INTERNAL_WRITE.reset(token)


def is_internal_write():
    '''Return ``True`` while MaRDMO itself is writing values (see :func:`internal_write`).'''
    return _INTERNAL_WRITE.get()


def find_reference(references, option_uri):
    '''Return the ``[option_uri, text]`` entry for *option_uri* in a reference dict, or ``None``.

    Reference and documentation answers are stored as
    ``{collection_index: [option_uri, text]}``.  The collection index is the
    option's position in the questionnaire, so entries are looked up by
    option rather than by position.
    '''
    for entry in (references or {}).values():
        if entry and entry[0] == option_uri:
            return entry
    return None


class PropertyRegistry:
    """Registry class to look up MathModDB / MathAlgoDB properties by key, label, or URL.

    Each entry in *properties* must be a dict with ``key``, ``label``, and
    ``url`` fields.  The registry builds three internal indices so that any
    of the three identifiers can be used for O(1) lookups via :meth:`get`.
    """
    def __init__(self, properties):
        '''Build lookup indices from *properties*.

        Args:
            properties: Iterable of dicts, each containing ``key``,
                        ``label``, and ``url`` string fields.
        '''
        self._by_key = {}
        self._by_label = {}
        self._by_url = {}

        for item in properties:
            entry = {
                "key":   item["key"],
                "label": item["label"],
                "url":   item["url"],
            }
            self._by_key[item["key"]]     = entry
            self._by_label[item["label"]] = entry
            self._by_url[item["url"]]     = entry

    def get(self, *, key=None, label=None, url=None) -> dict | None:
        """Look up a property by any field. Pass exactly one keyword arg."""
        if key is not None:
            return self._by_key.get(key)
        if label is not None:
            return self._by_label.get(label)
        if url is not None:
            return self._by_url.get(url)
        raise ValueError("Provide exactly one of: key, label, url")

def topological_order(direct_dependencies: dict[str, set[str]]) -> list[str]:
    '''Return nodes of a dependency graph in topological (creation) order.

    Uses Kahn's algorithm.  Nodes with no dependencies come first; nodes
    that depend on others follow after all their dependencies have been
    emitted.

    Args:
        direct_dependencies: Mapping ``{node: set_of_nodes_it_depends_on}``.

    Returns:
        Ordered list of node names.  If the graph is acyclic the list
        contains every node exactly once.
    '''
    dependents = defaultdict(set)
    in_degree = {}
    for item, deps in direct_dependencies.items():
        in_degree[item] = len(deps)
        for dep in deps:
            dependents[dep].add(item)
    queue = deque(item for item, deg in in_degree.items() if deg == 0)
    order = []
    while queue:
        item = queue.popleft()
        order.append(item)

        for dependent in dependents[item]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    return order

def is_cyclic(dependencies: dict[str, set[str]]) -> bool:
    '''Return ``True`` if the dependency graph contains a cycle (Kahn's algorithm).

    Args:
        dependencies: Mapping ``{node: set_of_nodes_it_depends_on}``.

    Returns:
        ``True`` if a cycle is detected, ``False`` if the graph is a DAG.
    '''
    dependents = defaultdict(set)
    in_degree = {}
    # Build in-degree and reverse edges
    for item, deps in dependencies.items():
        in_degree[item] = len(deps)
        for dep in deps:
            dependents[dep].add(item)
    # Nodes without dependencies
    queue = deque(item for item, deg in in_degree.items() if deg == 0)
    processed = 0
    while queue:
        item = queue.popleft()
        processed += 1
        for dependent in dependents[item]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    # If not all items were processed → cycle exists
    return processed != len(dependencies)

def date_format(parts: list) -> str | None:
    """Return a date string as YYYY-MM-DDT00:00:00Z given a list of date parts.

    Tolerates the shapes external sources deliver: numbers or strings, a
    missing (``None``) part, or a part with trailing text such as
    ``"13T10:00:00Z"``.  The date ends at the first missing or unreadable
    part, so ``[2020, None]`` gives a year-only date; ``None`` is returned
    if not even the year is readable.
    """
    numbers = []
    for part in (parts or [])[:3]:
        match = re.match(r'\s*(\d+)', str(part)) if part is not None else None
        if not match:
            break
        numbers.append(int(match.group(1)))
    if not numbers:
        return None
    year, month, day = (numbers + [0, 0])[:3]
    return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"

def date_precision(date_str: str) -> int | None:
    """
    Return Wikibase precision based on a date string.
    '+YYYY' -> 9, '+YYYY-MM' -> 10, '+YYYY-MM-DD' -> 11.
    """
    if not date_str:
        return None

    # Remove leading + and split date/time
    date_only = date_str.lstrip('+').split('T')[0]  # 'YYYY-MM-DD' or shorter
    parts = date_only.split('-')

    year = parts[0]
    month = parts[1] if len(parts) > 1 else '00'
    day = parts[2] if len(parts) > 2 else '00'

    if year != '0000':
        if month != '00':
            if day != '00':
                return 11  # day precision
            return 10  # month precision
        return 9  # year precision
    return None


def split_value(
    data: dict,
    key: str,
    transform: Optional[Callable[[str], Any]] = None,
    object_role: Optional[Callable[[Any], bool]] = None,
) -> list:
    """
    Split data[key]['value'] on ' <|> '. Optionally apply a transform
    to each element and filter the results with `object_role`.
    """
    if key not in data:
        return []

    raw = data.get(key, {}).get('value', '').split(" <|> ")

    parts = [part for part in raw if part]

    if transform is not None:
        parts = [transform(part) for part in parts]

    if object_role is not None:
        parts = [part for part in parts if object_role(part)]

    return parts

def basic_dict(value):
    '''Build a basic entity dict from an RDMO ``Value`` object.

    Extracts the label and description from the human-readable text of an
    ID question answer and returns them together with the external ID.

    Args:
        value: An RDMO :class:`~rdmo.projects.models.Value` instance whose
               ``text`` field follows the ``"Label (Description) [source]"``
               convention.

    Returns:
        Dict with keys ``ID``, ``Name``, and ``Description``.
    '''
    # Extract Label and Description from ID Question
    label, description, _ = extract_parts(value.text)
    # Return Basic Dict
    return {
        'ID': value.external_id,
        'Name': label,
        'Description': description
    }

def basic_list(value):
    '''Build a two-element list ``[option_uri, text]`` from an RDMO ``Value``.

    Args:
        value: An RDMO :class:`~rdmo.projects.models.Value` instance.

    Returns:
        ``[value.option_uri, value.text]``
    '''
    # Return Basic List
    return [
        value.option_uri,
        value.text
    ]

def define_setup(query_attributes, creation=False, query_id='', sources=None, item_class=None):
    """Build a query-setup dict used by provider ``get_options`` methods.

    Args:
        query_attributes: List of questionnaire attribute keys whose existing
                          values are surfaced as user-defined options.
        creation:         If ``True``, a "create new" option is prepended when
                          the search term is not found.
        query_id:         Identifier passed through to the query (optional).
        sources:          List of external sources to search (e.g.
                          ``['mardi', 'wikidata']``).  ``None`` defaults to
                          both sources inside the query helper.
        item_class:       Wikibase QID string or list of QID strings used to
                          restrict the MaRDI class-based search.

    Returns:
        Dict consumed by :func:`~MaRDMO.queries.query_sources_with_user_additions`.
    """
    return {
        'creation': creation,
        'query_attributes': query_attributes,
        'query_id': query_id,
        'sources': sources,
        'item_class': item_class,
    }

def nested_set(data, path, entry):
    """Set ``data[path[0]][path[1]]…[path[-1]] = entry``, creating intermediate dicts.

    Args:
        data:  Root dict to update in place.
        path:  Sequence of keys describing the nested location.
        entry: Value to store at the leaf.
    """
    d = data
    for key in path[:-1]:
        d = d.setdefault(key, {})
    d[path[-1]] = entry

def extract_parts(string):
    '''Extract the label, description, and source tag from an ID question text string.

    Expected format: ``"Label (Description) [source]"``.  Falls back gracefully
    when the format is incomplete.

    Args:
        string: ID question text value, typically produced by RDMO provider
                ``get_options`` calls (e.g. ``"Euler method (algorithm) [mardi]"``).

    Returns:
        Tuple ``(label, description, source)`` of extracted string components.
        *source* defaults to ``"user"`` when the bracket suffix is absent but
        the string ends with ``)``.
    '''
    # Step 1: Split the string at the last occurrence of ') [' to isolate source
    parts = string.rsplit(') [', 1)
    if len(parts) == 2:
        main_part, c = parts[0].strip(), parts[1].rstrip(']')
    else:
        main_part = parts[0].strip()
        if main_part.endswith(')'):
            main_part, c = main_part.rstrip(')'), "user"
        else:
            c = ""
    # Step 2: Find the last whitespace outside brackets to split
    depth = 0
    split_index = -1
    for i, char in enumerate(main_part):
        if char in ('(', '['):
            depth += 1
        elif char in (')', ']'):
            depth -= 1
        elif char == ' ' and depth == 0:
            split_index = i  # Update split_index to last whitespace outside brackets
    if split_index != -1:
        a = main_part[:split_index].strip()
        b = main_part[split_index+1:].strip().lstrip('(')  # Strip any leading '('
    else:
        a, b = main_part, ""
    return a, b, c

def value_editor(project, uri, info):
    '''Create or update a single RDMO questionnaire :class:`~rdmo.projects.models.Value`.

    Looks up the :class:`~rdmo.domain.models.Attribute` for *uri* and calls
    ``Value.objects.update_or_create`` with whichever of the optional *info*
    keys are present.

    Args:
        project: RDMO project instance that owns the value.
        uri:     Full attribute URI (``BASE_URI + path``).
        info:    Dict of optional fields to write.  Recognised keys:

                 * ``text``             – free-text answer
                 * ``external_id``      – external identifier (e.g. Wikidata QID)
                 * ``option``           – option URI string (resolved to an
                   :class:`~rdmo.options.models.Option` instance)
                 * ``collection_index`` – position within a collection question
                 * ``set_index``        – page index within a repeating set
                 * ``set_prefix``       – parent set index for nested sets

    Returns:
        Tuple ``(obj, created)`` as returned by ``update_or_create``.
    '''
    attribute_object = Attribute.objects.get(uri=uri)
    # Prepare the defaults dictionary
    defaults = {
        'project': project,
        'attribute': attribute_object,
    }

    if info.get('text') is not None:
        defaults['text'] = info['text']

    if info.get('external_id') is not None:
        defaults['external_id'] = info['external_id']

    if info.get('option') is not None:
        defaults['option'] = Option.objects.get(uri=info['option'])

    # Prepare the fields for update_or_create
    update_fields = {
        'project': project,
        'snapshot': None,
        'attribute': attribute_object,
        'defaults': defaults
    }

    if info.get('collection_index') is not None:
        update_fields['collection_index'] = info['collection_index']

    if info.get('set_index') is not None:
        update_fields['set_index'] = info['set_index']

    if info.get('set_prefix') is not None:
        update_fields['set_prefix'] = info['set_prefix']

    # Update or create the value
    with internal_write():
        obj, created = Value.objects.update_or_create(**update_fields)

    return obj, created

def check_list(list_var):
    '''Ensure *list_var* is a list, wrapping scalar values if necessary.

    * ``None``  → ``[]``
    * non-list  → ``[list_var]``
    * list      → unchanged

    Args:
        list_var: Value to normalise.

    Returns:
        A list.
    '''
    if list_var is None:
        list_var = []
    elif not isinstance(list_var, list):
        list_var = [list_var]
    return list_var

def label_index_map(data, data_type):
    '''Build a list of label→index mappings for the given entity types.

    For each type key in *data_type*, constructs a dict mapping
    ``"Name (Description)"`` strings to their 0-based position within
    ``data[type_key]``.  Used by :func:`entity_relations` and
    :func:`map_entity` to resolve cross-references by human-readable label.

    Args:
        data:      Top-level answers dict.
        data_type: List of entity-type keys (e.g. ``['formulation', 'task']``).

    Returns:
        List of dicts, one per entry in *data_type*.
    '''
    label_to_index_maps = []
    for to_idx in data_type:
        label_to_index_maps.append(
            {
                f"{data[to_idx][k].get('Name')} ({data[to_idx][k].get('Description')})": idx
                for idx, k in enumerate(data.get(to_idx, {}))
            }
        )
    return label_to_index_maps

def resolve_target(name, description, id_, entity_enc, label_map):
    """Resolve an entity reference to a local index string or fall back to its external ID.

    Looks up ``"name (description)"`` in *label_map*.  If found, returns the
    prefixed index (e.g. ``"MF3"``); otherwise returns *id_* unchanged.

    Args:
        name:        Human-readable label of the target entity.
        description: Short description of the target entity.
        id_:         Fallback external ID string.
        entity_enc:  Prefix string for locally indexed entities (e.g. ``"MF"``).
        label_map:   Dict mapping ``"Name (Description)"`` to 0-based index.

    Returns:
        Local index string or *id_*.
    """
    label_description = f"{name} ({description})"
    if label_description in label_map:
        return f"{entity_enc}{label_map[label_description] + 1}"
    return id_

def build_new_value(from_entry, entity, key, resolved, order, assumption, mapping):
    """Assemble the processed relation dict for a single relatant.

    Combines the resolved relatant reference with the relation type and
    optional order/assumption qualifiers into the dict format expected by
    the preview templates.

    Args:
        from_entry: Source entity dict (one entry from the answers).
        entity:     Configuration dict with keys ``relation``, ``old_name``,
                    ``new_name``, and ``encryption``.
        key:        Relation key within *from_entry*.
        resolved:   Resolved relatant reference (local index or external ID).
        order:      Dict with boolean flags ``formulation`` and ``task``
                    controlling which order qualifier is attached.
        assumption: Boolean; if ``True``, attach assumption qualifier.
        mapping:    :class:`~MaRDMO.helpers.PropertyRegistry` for relation lookup.

    Returns:
        Processed relation dict, or *resolved* unchanged when no relation is set.
    """
    if not entity['relation']:
        return resolved

    if not resolved:
        resolved = 'MISSING OBJECT ITEM'

    relation_value = from_entry.get(entity['relation'], {}).get(
        key, "MISSING RELATION TYPE"
    )

    new_value = {
            'relation': mapping.get(url=relation_value),
            'relatant': resolved
        }

    if order['formulation']:
        new_value.update(
            {
                'order': from_entry.get('formulation_number', {}).get(key)
            }
        )

    if order['task']:
        new_value.update(
            {
                'order': from_entry.get('task_number', {}).get(key)
            }
        )

    if assumption:
        new_value.update(
            {
                'assumption': from_entry.get('assumptionMapped', {}).get(key)
            }
        )

    return new_value


def entity_relations(data, idx, entity, order, assumption, mapping):
    """Resolve cross-entity relations and write processed entries into *data*.

    For every source entity in ``data[idx['from']]``, iterates over its raw
    relation and relatant keys, resolves each relatant against the label maps
    built from ``data[idx['to']]``, and stores the result under
    ``entity['new_name']``.  Handles both flat (single relatant) and nested
    (multiple relatants per relation) structures.

    Args:
        data:       Top-level answers dict; mutated in place.
        idx:        Dict with keys ``from`` (source type) and ``to`` (list of
                    target types used for label resolution).
        entity:     Dict with keys ``relation``, ``old_name``, ``new_name``,
                    and ``encryption``.
        order:      Dict with boolean flags ``formulation`` and ``task``.
        assumption: Boolean controlling assumption qualifier attachment.
        mapping:    :class:`~MaRDMO.helpers.PropertyRegistry` for relation type lookup.
    """
    idx['to'] = check_list(idx.get('to'))
    entity['encryption'] = check_list(entity['encryption'])
    label_to_index_maps = label_index_map(data, idx['to'])

    for from_entry in data.get(idx.get('from'), {}).values():
        # Get and combine Relation and Relatant Keys
        relation_keys = from_entry.get(entity['relation'], {}).keys()
        old_name_keys = from_entry.get(entity['old_name'], {}).keys()
        # Got through Relation and Relatant Keys
        for key in relation_keys | old_name_keys:
            # Get Relatants with old Names
            values = from_entry.get(entity['old_name'], {}).get(key,{})
            # Set Up Dict for Processed Names
            entity_values = from_entry.setdefault(entity['new_name'], {})
            # Check if Dict is flat
            if not is_flat(values):
                # Handle non-flat dicts
                for key2 in from_entry[entity['old_name']][key]:
                    value = from_entry[entity['old_name']][key][key2]
                    # Resolve Relatant
                    resolved = None
                    if value:
                        for enc_entry, label_map in zip(entity['encryption'], label_to_index_maps):
                            resolved = resolve_target(
                                name=value.get("Name"),
                                description=value.get("Description"),
                                id_=value.get("ID"),
                                entity_enc=enc_entry,
                                label_map=label_map,
                            )
                            if resolved != value.get("ID"):
                                break

                    # Build new Item Value
                    new_value = build_new_value(
                        from_entry,
                        entity,
                        key,
                        resolved,
                        order,
                        assumption,
                        mapping
                    )

                    # Add Process Item to Dict
                    if new_value not in entity_values.values():
                        entity_values[f"{key}|{key2}"] = new_value
            else:
                #Handle flat dicts
                resolved = None
                for enc_entry, label_map in zip(entity['encryption'], label_to_index_maps):
                    resolved = resolve_target(
                        name=values.get("Name"),
                        description=values.get("Description"),
                        id_=values.get("ID"),
                        entity_enc=enc_entry,
                        label_map=label_map,
                    )
                    if resolved != values.get("ID"):
                        break
                # Build new Item Value
                new_value = build_new_value(from_entry, entity, key, resolved, order, assumption, mapping)
                if new_value not in entity_values.values():
                    entity_values[key] = new_value

def entity_relations_grouped(data, idx, entity, order, assumption, mapping):
    """Resolve cross-entity relations without value-level deduplication.

    Identical to :func:`entity_relations` except that every resolved entry is
    always written, even when its value already appears under a different key.
    This is required for grouped structures where the same external ID (e.g.
    ``'not found'``) or the same platform software legitimately occurs at
    multiple set-indices.

    Args:
        data:       Top-level answers dict; mutated in place.
        idx:        Dict with keys ``from`` and ``to``.
        entity:     Dict with keys ``relation``, ``old_name``, ``new_name``,
                    and ``encryption``.
        order:      Dict with boolean flags ``formulation`` and ``task``.
        assumption: Boolean controlling assumption qualifier attachment.
        mapping:    :class:`~MaRDMO.helpers.PropertyRegistry` for relation type lookup.
    """
    idx['to'] = check_list(idx.get('to'))
    entity['encryption'] = check_list(entity['encryption'])
    label_to_index_maps = label_index_map(data, idx['to'])

    for from_entry in data.get(idx.get('from'), {}).values():
        relation_keys = from_entry.get(entity['relation'], {}).keys()
        old_name_keys = from_entry.get(entity['old_name'], {}).keys()
        for key in relation_keys | old_name_keys:
            values = from_entry.get(entity['old_name'], {}).get(key, {})
            entity_values = from_entry.setdefault(entity['new_name'], {})
            if not is_flat(values):
                for key2 in from_entry[entity['old_name']][key]:
                    value = from_entry[entity['old_name']][key][key2]
                    resolved = None
                    if value:
                        for enc_entry, label_map in zip(entity['encryption'], label_to_index_maps):
                            resolved = resolve_target(
                                name=value.get("Name"),
                                description=value.get("Description"),
                                id_=value.get("ID"),
                                entity_enc=enc_entry,
                                label_map=label_map,
                            )
                            if resolved != value.get("ID"):
                                break
                    new_value = build_new_value(
                        from_entry, entity, key, resolved, order, assumption, mapping
                    )
                    entity_values[f"{key}|{key2}"] = new_value
            else:
                resolved = None
                for enc_entry, label_map in zip(entity['encryption'], label_to_index_maps):
                    resolved = resolve_target(
                        name=values.get("Name"),
                        description=values.get("Description"),
                        id_=values.get("ID"),
                        entity_enc=enc_entry,
                        label_map=label_map,
                    )
                    if resolved != values.get("ID"):
                        break
                new_value = build_new_value(
                    from_entry, entity, key, resolved, order, assumption, mapping
                )
                entity_values[key] = new_value

def initialize_counter(counter):
    '''Return ``max(counter) + 1``, or ``0`` when *counter* is empty.

    Args:
        counter: Iterable of numeric values (e.g. existing set-index list).

    Returns:
        Next available integer index.
    '''
    return int(max(counter, default=-1)) + 1

def map_entity(data, idx, entity):
    '''Resolve entity references by label and store the result under a new key.

    Similar to :func:`entity_relations` but for simple label-to-index
    mappings (without relation types).  Iterates nested ``old_name`` entries
    in every source entity and writes resolved references into ``new_name``.

    Args:
        data:   Top-level answers dict; mutated in place.
        idx:    Dict with keys ``from`` (source type) and ``to`` (target
                types for label resolution).
        entity: Dict with keys ``old_name``, ``new_name``, and ``encryption``.
    '''
    # Ensure idx['to'] and enc are lists
    idx['to'] = check_list(idx['to'])
    entity['encryption'] = check_list(entity['encryption'])

    # Create mappings for all idx['to'] lists
    label_to_index_maps = label_index_map(data, idx['to'])
    # Use Template or Ressource Label
    for from_entry in data.get(idx['from'], {}).values():
        for outer_key, relation in from_entry.get(entity['old_name'], {}).items():
            for inner_key, item in relation.items():
                match_found = False
                # Create Dict Entry
                outer = from_entry.setdefault(entity['new_name'], {})
                inner = outer.setdefault(outer_key, {})
                for enc_entry, label_to_index in zip(entity['encryption'], label_to_index_maps):
                    if f"{item['Name']} ({item['Description']})" in label_to_index:
                        label_idx = label_to_index[f"{item['Name']} ({item['Description']})"]
                        match_found = True
                        inner[inner_key] = f"{enc_entry}{label_idx+1}"
                        break

                if not match_found:
                    inner[inner_key] = item['ID']

def process_qualifier(value):
    '''Parse a compound qualifier string into a structured dict.

    The expected format is entries separated by ``' <<||>> '``, where each
    entry has the form ``"id || label || description"``.

    Args:
        value: Raw qualifier string from the questionnaire.

    Returns:
        Dict mapping integer index to ``{id, label, description, source}``.
    '''
    # Create Value Dictionary
    value_dict = {}
    # Get splitted Values
    value_splitted = value.split(' <<||>> ')
    for value_idx, value_text in enumerate(value_splitted):
        # Extract Value ID, Label, and Description
        value_id, value_label, value_description = value_text.split(' || ')
        # Get Value Source
        value_source, _ = value_id.split(':')
        # Add to dict
        value_dict.update({value_idx: {'id': value_id,
                                       'label': value_label,
                                       'description': value_description,
                                       'source': value_source}})
    return value_dict


def reduce_prefix(prefix):
    '''Strip the ``|``-appended suffix from a set-prefix value and return the integer part.

    Prefixes stored in RDMO can be either plain integers or strings of the
    form ``"3|1"`` (parent index ``|`` child index).  This function always
    returns the leading integer component.

    Args:
        prefix: Integer or string prefix value.

    Returns:
        Integer prefix.
    '''
    if isinstance(prefix, int):
        prefix_reduced = prefix
    else:
        prefix_reduced = int(prefix.split('|')[0])
    return prefix_reduced

def relation_exists(value, set_prefix_red, info, relation_id=None):
    '''Check whether a value–set (–relation) triple already exists in the questionnaire.

    Used by :func:`~MaRDMO.adders.add_relations_static` and
    :func:`~MaRDMO.adders.add_relations_flexible` to avoid duplicate entries.

    Args:
        value:           Relatant object with ``id``, ``label``, and
                         ``description`` attributes.
        set_prefix_red:  Reduced integer set-prefix of the parent entity.
        info:            Dict of existing DB values keyed by ``value_ids``,
                         ``set_prefix_ids``, ``texts``, and optionally ``rels``.
        relation_id:     Option URI of the relation type; when provided the
                         check also verifies that the relation type matches.

    Returns:
        ``True`` if the combination is already present, ``False`` otherwise.
    '''

    # Case: relation check required
    if relation_id and "rels" in info:
        return any(
            (
                (f"{value.label} ({value.description})" == text or vid == value.id)
                and int(sid) == set_prefix_red
                and rel == relation_id
            )
            for vid, sid, rel, text in zip(
                info['value_ids'],
                info['set_prefix_ids'],
                info['rels'],
                info['texts'],
            )
        )

    # Case: only value + set check
    return any(
        (
            (f"{value.label} ({value.description})" == text or vid == value.id)
            and int(sid) == set_prefix_red
        )
        for vid, sid, text in zip(
            info['value_ids'],
            info['set_prefix_ids'],
            info['texts']
        )
    )

def relevant_set_ids(info, set_prefix_red):
    '''Return all set-index values whose set-prefix matches *set_prefix_red*.

    Args:
        info:           Dict containing parallel lists ``set_index_ids`` and
                        ``set_prefix_ids``.
        set_prefix_red: Reduced integer set-prefix to filter by.

    Returns:
        List of matching set-index integers.
    '''
    relevant_set_ids_list = []
    for set_index, set_prefix in zip(info['set_index_ids'], info['set_prefix_ids']):
        if set_prefix == set_prefix_red:
            relevant_set_ids_list.append(set_index)
    return relevant_set_ids_list

def replace_in_dict(d, target, replacement):
    '''Recursively replace all occurrences of *target* with *replacement* in *d*.

    Traverses nested dicts and lists, replacing string values that equal
    *target*.  Used after a Wikibase item is created to substitute the
    temporary ``Item<n>`` placeholder with the real QID.

    Args:
        d:           Dict, list, string, or scalar to process.
        target:      String to search for.
        replacement: Replacement string.

    Returns:
        A new structure with replacements applied (strings are new objects;
        dicts and lists are rebuilt recursively).
    '''
    if isinstance(d, dict):
        return {k: replace_in_dict(v, target, replacement) for k, v in d.items()}
    if isinstance(d, list):
        return [replace_in_dict(v, target, replacement) for v in d]
    if isinstance(d, str):
        return d.replace(target, replacement)
    return d

def collect_items_without_section(data, parent_key, child_key, nested=False):
    '''Collect and deduplicate child items that have no dedicated questionnaire section.

    Gathers all entries stored under *child_key* on every parent entity in
    *parent_key* and returns them as a flat, deduplicated dict keyed by
    consecutive integers.  Useful for exporting items like programming languages
    that are entered inline on a parent page rather than in their own section.

    Args:
        data:       Top-level answers dict.
        parent_key: Key of the parent entity group (e.g. ``"software"``).
        child_key:  Key of the inline child collection (e.g. ``"programminglanguage"``).
        nested:     When ``True``, treat the child collection as doubly nested
                    ``{outer_idx: {inner_idx: item}}`` rather than the default
                    ``{idx: item}``.  Use this for keys like ``MRelatant`` where
                    multiple items can appear per outer index.

    Returns:
        Dict mapping ``0, 1, 2, …`` to the deduplicated child item dicts.
    '''
    seen = set()
    result = {}
    for entity in data.get(parent_key, {}).values():
        col = entity.get(child_key, {})
        items = (
            item
            for inner in col.values()
            for item in inner.values()
        ) if nested else col.values()
        for item in items:
            key = (item.get('ID', ''), item.get('Name', ''), item.get('Description', ''))
            if key not in seen:
                seen.add(key)
                result[len(result)] = item
    return result


def unique_items(data, title = None):
    '''Collect all unique items referenced anywhere in *data*.

    Recursively walks the nested answers dict and returns every sub-dict
    that contains an ``ID`` key exactly once.  An optional workflow *title*
    item is prepended as ``Item0000000000``.

    Args:
        data:  Top-level answers dict.
        title: Optional workflow title string.  When provided, a placeholder
               item for the workflow itself is added first.

    Returns:
        Tuple ``(items, dependency)`` where *items* maps ``"Item<n>"`` keys to
        ``{ID, Name, Description, orcid, zbmath, issn}`` dicts and *dependency*
        maps the same keys to empty sets (populated later by
        :class:`~MaRDMO.payload.GeneratePayload`).
    '''
    # Set up Item Dict and track seen Items
    items = {}
    dependency = {}
    seen_items = set()
    # Add Workflow Item
    if title:
        triple = (
            'not found',
            title,
            data.get('general', {}).get('objective', '')
        )
        items[f'Item{str(0).zfill(10)}'] = {
            'ID': 'not found',
            'Name': title,
            'Description': data.get('general', {}).get('objective', '')
        }
        seen_items.add(triple)
        dependency.update({f'Item{str(0).zfill(10)}': set()})
    # Add Workflow Component Items
    def search(subdict):
        '''Search unique Items'''
        if isinstance(subdict, dict) and 'ID' in subdict:
            triple = (
                subdict.get('ID', ''),
                subdict.get('Name', ''),
                subdict.get('Description', ''),
                subdict.get('orcid', ''),
                subdict.get('zbmath', ''),
                subdict.get('issn', '')
            )
            if triple not in seen_items:
                item_key = f'Item{str(len(items)).zfill(10)}'  # Create unique key
                items[item_key] = {
                    'ID': triple[0],
                    'Name': triple[1],
                    'Description': triple[2],
                    'orcid': triple[3],
                    'zbmath': triple[4],
                    'issn': triple[5]
                }
                seen_items.add(triple)
                dependency.update({item_key: set()})
        if isinstance(subdict, dict):
            for value in subdict.values():
                if isinstance(value, dict):
                    search(value)
    search(data)
    return items, dependency

def process_question_dict(project, questions, get_answer):
    """Iterate through the nested questions dict and collect answers via *get_answer*.

    Walks every group in *questions*, skips group-level ``"uri"`` entries,
    fills in optional config defaults, then delegates each question config to
    *get_answer* to populate and return the answers dict.

    Args:
        project:    RDMO project instance.
        questions:  Nested questions dict as loaded from ``questions.json``.
        get_answer: Callable ``(project, answers, config) → answers`` that
                    extracts a single question's answer and merges it into
                    the running *answers* dict.

    Returns:
        Flat answers dict built by successive *get_answer* calls.
    """
    answers = {}

    for group in questions.values():
        for sub_key, config in group.items():
            if sub_key == "uri":
                continue  # Skip the group-level URI

            if not isinstance(config, dict) or "uri" not in config:
                continue  # Skip invalid or metadata-only entries

            # Fill in optional/default values
            config = {
                "key1": config.get("key1"),
                "key2": config.get("key2"),
                "key3": config.get("key3"),
                "uri": config["uri"],
                "set_prefix": config.get("set_prefix", False),
                "set_index": config.get("set_index", False),
                "collection_index": config.get("collection_index", False),
                "external_id": config.get("external_id", False),
                "option_text": config.get("option_text", False),
            }

            # Call the injected function
            answers = get_answer(
                project,
                answers,
                config
            )

    return answers

def compare_items(old, new, wikidata_qid_prop=None):
    """Return a mapping of newly created items indexed by (label, description).

    Compares the ``id`` field of every ``Item*`` key: entries that had no id
    before posting (``old[key]['id']`` is falsy) and have one afterwards are
    collected together with the original external ID and the new QID.
    Items still without id (export aborted before they were posted) are
    skipped.

    The original external ID is inferred from the item's statements: items
    that carry a Wikidata QID external-id statement are tagged as
    ``wikidata:<QID>``; all others are tagged as ``not found``.

    Args:
        old:                Deep copy of the payload dict taken *before* posting.
        new:                Payload dict *after* posting (ids filled in by Wikibase).
        wikidata_qid_prop:  Property ID string for the Wikidata QID property
                            (e.g. ``'P123'``), used to detect Wikidata-sourced
                            items.  Pass ``get_properties().get('Wikidata QID')``.

    Returns:
        Dict mapping ``(label, description)`` tuples to
        ``{'old_id': <original external id>, 'new_qid': <assigned QID>}``.
    """

    created = {}
    for key, value in old.items():
        if key.startswith('Item') and not value['id'] and new[key].get('id'):
            item = new[key]
            label = item['payload']['item']['labels']['en']
            description = item['payload']['item'].get('descriptions', {}).get('en', '')

            # Detect wikidata items by presence of the Wikidata QID statement.
            old_id = 'not found'
            if wikidata_qid_prop:
                for stmt in value.get('statements', []):
                    if stmt[0] == wikidata_qid_prop and stmt[1] == 'external-id':
                        old_id = f'wikidata:{stmt[2]}'
                        break

            created[(label, description)] = {
                'old_id':  old_id,
                'new_qid': item['id'],
                'class':   old[key].get('class', ''),
            }
    return created


def collect_statements(init, jsons, pid_to_name=None, qid_to_name=None):
    """Extract newly added statements as human-readable triples after a portal export.

    Covers two sources:

    - ``RELATION<n>`` entries that were posted to existing items (the portal
      returned a statement id; entries that already existed or were not
      reached before an aborted export have none).
    - Statements embedded in newly created ``Item<n>`` entries (items that had
      no id before posting).

    Args:
        init:         Deep copy of the payload taken *before* posting (used to
                      distinguish new vs. pre-existing items).
        jsons:        Payload dict *after* posting (all ``Item<n>`` placeholders
                      replaced with real QIDs by :func:`replace_in_dict`).
        pid_to_name:  Dict mapping Wikibase property IDs to human-readable names
                      (i.e. the inverse of ``get_properties()``).
        qid_to_name:  Dict mapping Wikibase item QIDs to human-readable names
                      (i.e. the inverse of ``get_items()``).

    Returns:
        List of ``[subject_label, subject_qid, property_name, object_label,
        object_qid, qualifiers]`` lists, JSON-serializable.  ``object_qid`` is
        an empty string for non-item value types.  ``qualifiers`` is a list of
        ``{"prop": name, "obj": label, "obj_qid": qid}`` dicts.
    """
    pid_to_name = pid_to_name or {}
    qid_to_name = qid_to_name or {}

    qid_to_label = {
        v['id']: v['label']
        for k, v in jsons.items()
        if k.startswith('Item') and v.get('id') and v.get('label')
    }

    def _resolve(qid):
        """Return a human-readable label for *qid*, falling back to the raw QID."""
        return qid_to_label.get(qid) or qid_to_name.get(qid) or qid

    def _format_value(datatype, value):
        """Convert a Wikibase statement value to a ``(display_string, obj_qid)`` pair.

        *obj_qid* is non-empty only for ``wikibase-item`` values so the caller
        can render a portal link.  Special handling per datatype:

        - ``wikibase-item``    — resolves QID to label via ``_resolve``
        - ``quantity``         — strips leading ``+`` from amount (unit handled separately)
        - ``monolingualtext``  — extracts the ``text`` field
        - ``time``             — extracts the date portion (``YYYY-MM-DD``)
        - ``math``             — wraps in ``\\(…\\)`` for MathJax inline rendering
        """
        if datatype == 'wikibase-item' and isinstance(value, str):
            return _resolve(value), value
        if datatype == 'quantity' and isinstance(value, dict):
            return value.get('amount', '').lstrip('+'), ''
        if datatype == 'monolingualtext' and isinstance(value, dict):
            return value.get('text', str(value)), ''
        if datatype == 'time' and isinstance(value, dict):
            return value.get('time', '').lstrip('+').split('T')[0], ''
        if datatype == 'math':
            return f'\\({value}\\)', ''
        return str(value), ''

    def _get_unit(datatype, value):
        """Return ``(unit_label, unit_qid)`` for a quantity value with a named unit.

        Returns ``('', '')`` for non-quantity values or dimensionless quantities
        (unit ``"1"``).  The unit QID is extracted from the tail of the unit URL
        and resolved to a label via ``_resolve``.
        """
        if datatype != 'quantity' or not isinstance(value, dict):
            return '', ''
        u_qid = value.get('unit', '').rsplit('/', 1)[-1]
        if u_qid == '1':
            return '', ''
        return _resolve(u_qid), u_qid

    def _format_qualifiers(quals_raw):
        """Format a list of raw Wikibase qualifier dicts into display-ready dicts.

        Each output dict has keys ``prop`` (property label), ``obj`` (formatted
        value string), and ``obj_qid`` (portal QID or empty string).
        """
        result = []
        for q in quals_raw:
            q_prop_id = q.get('property', {}).get('id', '')
            q_dtype   = q.get('property', {}).get('data_type', 'string')
            q_val     = q.get('value', {}).get('content', '')
            q_prop_name      = pid_to_name.get(q_prop_id, q_prop_id)
            q_obj, q_obj_qid = _format_value(q_dtype, q_val)
            result.append({'prop': q_prop_name, 'obj': q_obj, 'obj_qid': q_obj_qid})
        return result

    statements = []

    # --- RELATION entries posted to existing items
    for key, entry in jsons.items():
        if not key.startswith('RELATION'):
            continue
        if entry.get('exists') == 'true' or not entry.get('id'):
            continue
        url = entry.get('url', '')
        parts = url.split('/items/')
        if len(parts) < 2:
            continue
        subject_qid   = parts[1].split('/')[0]
        subject_label = _resolve(subject_qid)
        stmt     = entry['payload']['statement']
        prop_id  = stmt['property']['id']
        datatype = stmt['property']['data_type']
        value    = stmt['value']['content']
        prop_name          = pid_to_name.get(prop_id, prop_id)
        obj_label, obj_qid = _format_value(datatype, value)
        unit_label, unit_qid = _get_unit(datatype, value)
        quals = _format_qualifiers(stmt.get('qualifiers', []))
        statements.append([subject_label, subject_qid, prop_name, obj_label, obj_qid, quals, unit_label, unit_qid])

    # --- Statements embedded in newly created items
    for key, entry in jsons.items():
        if not key.startswith('Item'):
            continue
        if init.get(key, {}).get('id'):  # was already on portal before posting
            continue
        subject_qid = entry.get('id', '')
        if not subject_qid:
            continue
        subject_label = entry.get('label', subject_qid)
        for stmt_tuple in entry.get('statements', []):
            if len(stmt_tuple) < 3:
                continue
            prop_id, datatype, value = stmt_tuple[0], stmt_tuple[1], stmt_tuple[2]
            quals_raw = stmt_tuple[3] if len(stmt_tuple) >= 4 else []
            prop_name          = pid_to_name.get(prop_id, prop_id)
            obj_label, obj_qid = _format_value(datatype, value)
            unit_label, unit_qid = _get_unit(datatype, value)
            quals = _format_qualifiers(quals_raw)
            statements.append([subject_label, subject_qid, prop_name, obj_label, obj_qid, quals, unit_label, unit_qid])

    return statements


# Entity types that have dedicated ID / Name / Description question pages.
# Used by replace_ids to locate sibling Values for 'not found' ID questions.
_ID_ENTITY_URIS = [
    'field', 'problem', 'model', 'formulation', 'quantity', 'task',
    'algorithm', 'software', 'benchmark', 'workflow', 'hardware',
    'dataset', 'processstep',
]


def replace_ids(project, created, base_uri):
    """Update RDMO project Values after a successful portal export.

    For every newly created MaRDI Portal item, finds all RDMO
    :class:`~rdmo.projects.models.Value` objects in *project* that still
    reference the old external ID and overwrites them with the new
    ``mardi:<QID>`` identifier.  Three cases are handled:

    - **Wikidata items**: matched by ``external_id`` directly; ``[wikidata]``
      is replaced by ``[mardi]`` in the text field.
    - **User-defined items in relation / inline questions** (text stores
      ``"label (description)"``): matched by parsing label + description from
      ``value.text`` via :func:`extract_parts`.
    - **User-defined items in ID questions** (text is ``"not found"``):
      matched by looking up sibling Name and Description Values at the same
      set index.

    Args:
        project:  RDMO project instance whose Values should be updated.
        created:  Dict as returned by :func:`compare_items` —
                  ``{(label, description): {'old_id': ..., 'new_qid': ...}}``.
        base_uri: RDMO base URI prefix (``BASE_URI`` from
                  :mod:`~MaRDMO.constants`).
    """

    # ------------------------------------------------------------------ #
    # Case A — wikidata items: one bulk query per export, matched by QID  #
    # ------------------------------------------------------------------ #
    wikidata_map = {
        info['old_id']: f"mardi:{info['new_qid']}"
        for (_, __), info in created.items()
        if info['old_id'].startswith('wikidata:')
    }
    if wikidata_map:
        for v in Value.objects.filter(
            project=project, snapshot=None, external_id__in=wikidata_map
        ).select_related('attribute'):
            v.external_id = wikidata_map[v.external_id]
            v.text = v.text.replace('[wikidata]', '[mardi]')
            with internal_write():
                v.save()

    # ------------------------------------------------------------------ #
    # Cases B1 + B2 — user-defined items ('not found')                   #
    # ------------------------------------------------------------------ #
    nf_map = {
        (label, desc): f"mardi:{info['new_qid']}"
        for (label, desc), info in created.items()
        if info['old_id'] == 'not found'
    }
    if not nf_map:
        return

    for v in Value.objects.filter(
        project=project, snapshot=None, external_id='not found'
    ).select_related('attribute'):

        if v.text == 'not found':
            # B2: ID question — resolve label+description via sibling Values
            entity = next(
                (e for e in _ID_ENTITY_URIS
                 if v.attribute.uri == base_uri + f'domain/{e}/id'),
                None
            )
            if entity is None:
                continue
            # Name/Description questions use set_prefix = parent set chain
            sibling_prefix = (
                f'{v.set_prefix}|{v.set_index}' if v.set_prefix
                else str(v.set_index)
            )
            try:
                v_label = Value.objects.get(
                    project=project,
                    snapshot=None,
                    attribute__uri=base_uri + f'domain/{entity}/name',
                    set_prefix=sibling_prefix,
                ).text
            except (Value.DoesNotExist, Value.MultipleObjectsReturned):
                continue
            try:
                v_desc = Value.objects.get(
                    project=project,
                    snapshot=None,
                    attribute__uri=base_uri + f'domain/{entity}/description',
                    set_prefix=sibling_prefix,
                ).text
            except (Value.DoesNotExist, Value.MultipleObjectsReturned):
                v_desc = ''
            key = (v_label, v_desc)
        else:
            # B1: relation / inline question — parse label+description from text
            v_label, v_desc, _ = extract_parts(v.text)
            key = (v_label, v_desc)

        if key in nf_map:
            label, desc = key
            v.external_id = nf_map[key]
            v.text = f'{label} ({desc}) [mardi]' if desc else f'{label} [mardi]'
            with internal_write():
                v.save()

def is_flat(d):
    """Return ``True`` if *d* is a dict whose values are all strings (or *d* is empty).

    Used by :func:`entity_relations` to distinguish single-relatant dicts
    from nested relatant-of-relatant structures.

    Args:
        d: Value to inspect.

    Returns:
        ``True`` for flat string-valued dicts; ``False`` otherwise.
    """
    if not isinstance(d, dict):
        return False
    if d == {}:
        return True
    return isinstance(next(iter(d.values())), str)


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
                ``"Label (Description) [source]"`` format.
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
