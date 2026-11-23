'''Utility functions for assembling model-entity data structures.

Provides helpers that map raw SPARQL result fields to the structured dicts
expected by handler and worker code when building model documentation entries.

Provides:

- ``build_quantity_info``   — construct a quantity/quantity-kind info dict from raw data
- ``map_entity_quantity``   — map an entity's quantity fields using the appropriate property list
'''


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

    For each entity of *entity_type* in *data*, links each element to the
    quantity page with the ID of the element's ``"quantity"`` and writes a
    ``"Info"`` key (built by :func:`build_quantity_info`) when there is one.
    Quantities are not matched by name: two quantities may share it.

    Args:
        data:        Top-level answers dict (mutated in place).
        entity_type: Key of the entity section to process (e.g.
                     ``"formulation"`` or ``"task"``).
    '''
    # Of two quantity pages with one ID (a copied tab) the first
    quantities = {}
    for quantity in data.get("quantity", {}).values():
        if quantity.get("ID"):
            quantities.setdefault(quantity["ID"], quantity)
    for entity in data.get(entity_type, {}).values():
        for element in entity.get("element", {}).values():
            # No quantity yet (e.g. a symbol without "symbol represents" on the
            # portal) or one without page: no Info
            quantity = quantities.get((element.get("quantity") or {}).get("ID"))
            if quantity is None:
                continue

            qtype = quantity.get("QorQK")

            if qtype in ('Quantity', 'Quantity Kind'):
                element["Info"] = build_quantity_info(quantity, qtype)
