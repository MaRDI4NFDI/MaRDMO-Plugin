'''Utility functions for assembling model-entity data structures.

Provides helpers that map raw SPARQL result fields to the structured dicts
expected by handler and worker code when building model documentation entries.

Provides:

- ``get_data_properties``   — return the list of data-property keys for a given entity type
- ``build_quantity_info``   — construct a quantity/quantity-kind info dict from raw data
- ``map_entity_quantity``   — map an entity's quantity fields using the appropriate property list
'''

from .constants import DEPENDENT_PROPERTIES, INDEPENDENT_PROPERTIES

from ..getters import get_items, get_mathmoddb

def get_data_properties(item_type):
    """Return a URL→QID mapping of data properties for the given *item_type*.

    Combines class-independent properties (the same for all entity types) with
    class-dependent properties whose Wikibase item QID is suffixed with the
    *item_type* string (e.g. ``"linear model"`` → ``"linear quantity"``).

    Args:
        item_type: Entity class string, e.g. ``"model"``, ``"task"``,
                   ``"quantity"``, or ``"quantity kind"``.

    Returns:
        Dict mapping MathModDB property URL to Wikibase item QID.
    """

    # Get MathModDB Mapping and Items
    mathmoddb = get_mathmoddb()
    items = get_items()

    # Add class-independent Properties
    properties = {
        mathmoddb.get(key=k)["url"]: items.get(label)
        for k, label in INDEPENDENT_PROPERTIES
    }

    # Add class-dependent Properties
    properties.update({
        mathmoddb.get(key=k)["url"]: items.get(f'{label} {item_type}')
        for k, label in DEPENDENT_PROPERTIES
    })

    return properties

def build_quantity_info(quantity, qtype):
    '''Build the ``Info`` sub-dict for a Quantity or QuantityKind element.

    Args:
        quantity: Answer sub-dict for a single quantity/quantity-kind entry.
        qtype:    Entity class string — ``"Quantity"`` or ``"Quantity Kind"``.
                  Quantity entries additionally receive ``QKName`` and ``QKID``
                  fields pointing to their associated Quantity Kind.

    Returns:
        Dict with keys ``"Type"``, ``"Name"``, ``"Description"``, ``"ID"``,
        and (for Quantity only) ``"QKName"`` and ``"QKID"``.
    '''
    base_info = {
        "Type": qtype,
        "Name": quantity.get("Name", ""),
        "Description": quantity.get("Description", ""),
        "ID": quantity.get("ID", ""),
    }

    # Only Quantity has QKRelatant
    if qtype == "Quantity":
        base_info["QKName"] = quantity.get("QKRelatant-Q", {}).get(0, {}).get(0, {}).get("Name", "")
        base_info["QKID"] = quantity.get("QKRelatant-Q", {}).get(0, {}).get(0, {}).get("ID", "")

    return base_info

def map_entity_quantity(data, entity_type):
    '''Attach Quantity/QuantityKind ``Info`` dicts to matching formula elements.

    For each entity of *entity_type* in *data*, matches each element's
    ``"quantity"`` name against the top-level ``"quantity"`` section and
    writes a ``"Info"`` key (built by :func:`build_quantity_info`) when a
    match is found.

    Args:
        data:        Top-level answers dict (mutated in place).
        entity_type: Key of the entity section to process (e.g.
                     ``"formulation"`` or ``"task"``).
    '''
    for entity in data.get(entity_type, {}).values():
        for element in entity.get("element", {}).values():
            element_quantity_name = element.get("quantity", {}).get("Name", "").lower()
            if not element_quantity_name:
                # No quantity yet (e.g. a symbol without "symbol represents" on
                # the portal): must not match a quantity page without a name
                continue

            for quantity in data.get("quantity", {}).values():
                quantity_name = quantity.get("Name", "").lower()

                if element_quantity_name != quantity_name:
                    continue

                qtype = quantity.get("QorQK")

                if qtype in ('Quantity', 'Quantity Kind'):
                    element["Info"] = build_quantity_info(quantity, qtype)
