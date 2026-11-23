'''Relations between the entries of a documentation, resolved to their pages for preview and export.'''
from .export.items import item_key
from .pages import page_refs


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


def build_new_value(from_entry, entity, key, resolved, assumption, mapping):
    """Assemble the processed relation dict for a single relatant.

    Combines the resolved relatant reference with the relation type and
    the optional assumption qualifier into the dict format expected by
    the preview templates.

    Args:
        from_entry: Source entity dict (one entry from the answers).
        entity:     Configuration dict with keys ``relation``, ``old_name``
                    and ``new_name``.
        key:        Relation key within *from_entry*.
        resolved:   Resolved relatant (:class:`~MaRDMO.pages.PageRef` or ID).
        assumption: Boolean; if ``True``, attach assumption qualifier.
        mapping:    :class:`~MaRDMO.core.properties.PropertyRegistry` for relation lookup.

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

    if assumption:
        new_value.update(
            {
                'assumption': from_entry.get('assumptionMapped', {}).get(key)
            }
        )

    return new_value


def entity_relations(data, idx, entity, assumption, mapping, grouped=False):
    """Resolve cross-entity relations and write processed entries into *data*.

    For every source entity in ``data[idx['from']]``, iterates over its raw
    relation and relatant keys, resolves each relatant to the page with its
    ID in ``data[idx['to']]``, and stores the result under
    ``entity['new_name']``.  Handles both flat (single relatant) and nested
    (multiple relatants per relation) structures.

    An entry equal to one already written is left out, unless *grouped*:
    grouped structures (the workflow's) hold the same item (e.g. the same
    own item, the same platform software) at several set indices.

    Args:
        data:       Top-level answers dict; mutated in place.
        idx:        Dict with keys ``from`` (source type) and ``to`` (list of
                    target types of the pages).
        entity:     Dict with keys ``relation``, ``old_name`` and ``new_name``.
        assumption: Boolean controlling assumption qualifier attachment.
        mapping:    :class:`~MaRDMO.core.properties.PropertyRegistry` for relation type lookup.
        grouped:    Write every entry, also one equal to an entry already written.
    """
    refs = page_refs(data, check_list(idx.get('to')))

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
                    resolved = refs.get(value.get('ID'), value.get('ID')) if value else None

                    # Build new Item Value
                    new_value = build_new_value(
                        from_entry,
                        entity,
                        key,
                        resolved,
                        assumption,
                        mapping
                    )

                    # Add Process Item to Dict
                    if grouped or new_value not in entity_values.values():
                        entity_values[f"{key}|{key2}"] = new_value
            else:
                #Handle flat dicts
                resolved = refs.get(values.get('ID'), values.get('ID'))
                # Build new Item Value
                new_value = build_new_value(from_entry, entity, key, resolved, assumption, mapping)
                if grouped or new_value not in entity_values.values():
                    entity_values[key] = new_value


def resolve_relations(data, relations, mappings, default):
    """Resolve the relations of a catalog's preview table in *data* (:func:`entity_relations` per row).

    Args:
        data:      Top-level answers dict; mutated in place.
        relations: The catalog's ``preview_relations``: rows with ``from_idx``,
                   ``to_idx``, ``relation``, ``old_name``, ``new_name`` and
                   optionally ``assumption``, ``grouped`` and ``mapping``.
        mappings:  ``{name: PropertyRegistry}`` for the rows' ``mapping``.
        default:   The :class:`~MaRDMO.core.properties.PropertyRegistry` of rows
                   without (or with another) ``mapping``.
    """
    for relation in relations:
        entity_relations(
            data = data,
            idx = {
                'from': relation['from_idx'],
                'to': relation['to_idx']
            },
            entity = {
                'relation': relation['relation'],
                'old_name': relation['old_name'],
                'new_name': relation['new_name']
            },
            assumption = relation.get('assumption', False),
            mapping = mappings.get(relation.get('mapping'), default),
            grouped = relation.get('grouped', False),
        )


def map_entity(data, idx, entity):
    '''Resolve entity references to their pages by ID and store the result under a new key.

    Similar to :func:`entity_relations` but without relation types: every
    nested ``old_name`` entry of a source entity becomes the
    :class:`~MaRDMO.pages.PageRef` of the page with its ID, or keeps the ID
    (an item without page), under ``new_name``.

    Args:
        data:   Top-level answers dict; mutated in place.
        idx:    Dict with keys ``from`` (source type) and ``to`` (target
                types of the pages).
        entity: Dict with keys ``old_name`` and ``new_name``.
    '''
    refs = page_refs(data, check_list(idx['to']))
    for from_entry in data.get(idx['from'], {}).values():
        for outer_key, relation in from_entry.get(entity['old_name'], {}).items():
            for inner_key, item in relation.items():
                inner = from_entry.setdefault(entity['new_name'], {}).setdefault(outer_key, {})
                inner[inner_key] = refs.get(item.get('ID'), item['ID'])


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
            key = item_key(item.get('ID', ''), item.get('Name', ''), item.get('Description', ''))
            if key not in seen:
                seen.add(key)
                result[len(result)] = item
    return result


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
