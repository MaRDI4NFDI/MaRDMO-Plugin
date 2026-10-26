'''Functional rules that map RDMO ``Value`` instances to structured dict entries.

Each rule handles one combination of the five flags ``(set_prefix, set_index,
collection_index, external_id, option_text)`` and determines how a
questionnaire value is extracted and where it is stored in the result dict.
All rules share the same call signature so they can be dispatched uniformly
via :data:`~MaRDMO.constants.flag_dict`, which maps each flag tuple to its rule.

Provides:

- ``rule_0`` … ``rule_19`` — individual rule implementations
'''

from .helpers import basic_dict, basic_list

def rule_0(value, attribute, config, _prefix_idx):
    '''Handle flag-combo 0: ``[key1, key2]`` path, raw attribute value.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:   Attribute name to read from *value* (e.g. ``'text'``).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *entry* is the attribute value and
        *path* is ``[key1, key2]``.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], config["key2"]]
    return entry, path

def rule_1(value, attribute, config, prefix_idx):
    '''Handle flag-combo 1: ``[key1, prefix_idx, key2]`` path, raw attribute value.

    Args:
        value:      RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:  Attribute name to read from *value*.
        config:     Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx: Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is the attribute value and
        *path* is ``[key1, prefix_idx, key2]``.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], prefix_idx, config["key2"]]
    return entry, path

def rule_2(value, attribute, config, _prefix_idx):
    '''Handle flag-combo 2: ``[key1, set_index, key2]`` path, raw attribute value.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:   Attribute name to read from *value*.
        config:      Question config dict with ``key1`` and ``key2`` entries.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *path* is ``[key1, set_index, key2]``.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], value.set_index, config["key2"]]
    return entry, path

def rule_3(value, attribute, config, prefix_idx):
    '''Handle flag-combo 3: ``[key1, prefix_idx, key2, set_index(, key3)]`` path.

    Args:
        value:      RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:  Attribute name to read from *value*.
        config:     Question config dict with ``key1``, ``key2``, and optional ``key3``.
        prefix_idx: Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *path* includes an optional ``key3`` tail.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], prefix_idx, config["key2"], value.set_index]
    if config["key3"]:
        path.append(config["key3"])
    return entry, path

def rule_4(value, attribute, config, _prefix_idx):
    '''Handle flag-combo 4: ``[key1, set_index, key2, collection_index(, key3)]`` path, raw attribute value.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:   Attribute name to read from *value*.
        config:      Question config dict with ``key1``, ``key2``, and optional ``key3``.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *entry* is the raw attribute value and
        *path* includes an optional ``key3`` tail.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], value.set_index, config["key2"], value.collection_index]
    if config["key3"]:
        path.append(config["key3"])
    return entry, path

def rule_5(value, attribute, config, prefix_idx):
    '''Handle flag-combo 5: ``[key1, prefix_idx, key2, collection_index]`` path, raw attribute value.

    Args:
        value:      RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:  Attribute name to read from *value*.
        config:     Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx: Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is the raw attribute value and
        *path* is ``[key1, prefix_idx, key2, collection_index]``.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], prefix_idx, config["key2"], value.collection_index]
    return entry, path

def rule_6(value, _attribute, config, prefix_idx):
    '''Handle flag-combo 6: ``[key1, prefix_idx, key2, set_index, collection_index]`` path, option list entry.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx:  Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``[option_uri, text]``.
    '''
    entry = basic_list(value)
    path = [config["key1"], prefix_idx, config["key2"], value.set_index, value.collection_index]
    return entry, path

def rule_19(value, attribute, config, prefix_idx):
    '''Handle flag-combo 19: ``[key1, prefix_idx, key2, set_index, collection_index]`` path, raw attribute value.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:   Attribute name to read from *value*.
        config:      Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx:  Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is the raw attribute value and
        *path* is ``[key1, prefix_idx, key2, set_index, collection_index]``.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], prefix_idx, config["key2"], value.set_index, value.collection_index]
    return entry, path

def rule_7(value, _attribute, config, prefix_idx):
    '''Handle flag-combo 7: ``[key1, prefix_idx, key2]`` path, option list entry.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx:  Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``[option_uri, text]``.
    '''
    entry = basic_list(value)
    path = [config["key1"], prefix_idx, config["key2"]]
    return entry, path

def rule_8(value, _attribute, config, _prefix_idx):
    '''Handle flag-combo 8: ``[key1, set_index, key2]`` path, option list entry.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``[option_uri, text]``.
    '''
    entry = basic_list(value)
    path = [config["key1"], value.set_index, config["key2"]]
    return entry, path

def rule_9(value, _attribute, config, _prefix_idx):
    '''Handle flag-combo 9: top-level ``[key1]`` path, basic entity dict.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with a ``key1`` entry.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``{ID, Name, Description}``
        and *path* is ``[key1]``.
    '''
    entry = basic_dict(value)
    path = [config["key1"]]
    return entry, path

def rule_10(value, attribute, config, _prefix_idx):
    '''Handle flag-combo 10: ``[key1, key2, collection_index]`` path, raw attribute value.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:   Attribute name to read from *value*.
        config:      Question config dict with ``key1`` and ``key2`` entries.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *path* is ``[key1, key2, collection_index]``.
    '''
    entry = getattr(value, attribute)
    path = [config["key1"], config["key2"], value.collection_index]
    return entry, path

def rule_11(value, _attribute, config, _prefix_idx):
    '''Handle flag-combo 11: ``[key1, key2, collection_index]`` path, basic entity dict.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``{ID, Name, Description}``.
    '''
    entry = basic_dict(value)
    path = [config["key1"], config["key2"], value.collection_index]
    return entry, path

def rule_12(value, _attribute, config, _prefix_idx):
    '''Handle flag-combo 12: ``[key1, set_index, key2]`` path, external ID value.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``value.external_id``.
    '''
    entry = value.external_id
    path = [config["key1"], value.set_index, config["key2"]]
    return entry, path

def rule_13(value, _attribute, config, prefix_idx):
    '''Handle flag-combo 13: ``[key1, prefix_idx, key2, set_index(, key3)]`` path, entity dict.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1``, ``key2``, and optional ``key3``.
        prefix_idx:  Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``{ID, Name, Description}``
        and *path* includes an optional ``key3`` tail.
    '''
    entry = basic_dict(value)
    path = [config["key1"], prefix_idx, config["key2"], value.set_index]
    if config["key3"]:
        path.append(config["key3"])
    return entry, path

def rule_14(value, _attribute, config, prefix_idx):
    '''Handle flag-combo 14: ``[key1, prefix_idx, key2, collection_index]`` path, entity dict.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx:  Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``{ID, Name, Description}``.
    '''
    entry = basic_dict(value)
    path = [config["key1"], prefix_idx, config["key2"], value.collection_index]
    return entry, path

def rule_15(value, _attribute, config, prefix_idx):
    '''Handle flag-combo 15: ``[key1, prefix_idx, key2, set_index, collection_index]`` path, entity dict.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx:  Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``{ID, Name, Description}``.
    '''
    entry = basic_dict(value)
    path = [config["key1"], prefix_idx, config["key2"], value.set_index, value.collection_index]
    return entry, path

def rule_16(value, attribute, config, prefix_idx):
    '''Handle flag-combo 16: ``[key1, prefix_idx, key2, set_index(, key3)]`` path.

    Args:
        value:      RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:  Attribute name to read from *value*.
        config:     Question config dict with ``key1``, ``key2``, and optional ``key3``.
        prefix_idx: Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *path* includes an optional ``key3`` tail.
    '''
    entry = basic_list(value)
    path = [config["key1"], prefix_idx, config["key2"], value.set_index]
    if config["key3"]:
        path.append(config["key3"])
    return entry, path

def rule_17(value, _attribute, config, prefix_idx):
    '''Handle flag-combo 17: ``[key1, prefix_idx, key2, collection_index]`` path, option list entry.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1`` and ``key2`` entries.
        prefix_idx:  Current set-prefix index.

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``[option_uri, text]`` and
        *path* is ``[key1, prefix_idx, key2, collection_index]``.
    '''
    entry = basic_list(value)
    path = [config["key1"], prefix_idx, config["key2"], value.collection_index]
    return entry, path

def rule_18(value, _attribute, config, _prefix_idx):
    '''Handle flag-combo 18: ``[key1, set_index, key2, collection_index(, key3)]`` path, option list entry.

    Args:
        value:       RDMO :class:`~rdmo.projects.models.Value` instance.
        _attribute:  Unused (present for uniform call signature).
        config:      Question config dict with ``key1``, ``key2``, and optional ``key3``.
        _prefix_idx: Unused (present for uniform call signature).

    Returns:
        Tuple ``(entry, path)`` where *entry* is ``[option_uri, text]`` and
        *path* includes an optional ``key3`` tail.
    '''
    entry = basic_list(value)
    path = [config["key1"], value.set_index, config["key2"], value.collection_index]
    if config["key3"]:
        path.append(config["key3"])
    return entry, path
