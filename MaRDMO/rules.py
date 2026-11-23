'''Where a questionnaire value goes in the answers dict (#138).

A question of ``questions.json`` names its place in the answers with the keys
``key1``, ``key2`` and an optional ``key3``, and five flags: ``set_prefix``,
``set_index``, ``collection_index``, ``external_id`` and ``option_text``.
:func:`route` turns a value of the question into its entry and the path of
the entry; :func:`~MaRDMO.project.answers.get_answers` writes it there.

The path is ``key1``, then the set prefix (``set_prefix``), ``key2``, the set
index (``set_index``), the collection index (``collection_index``) and
``key3``.  Without a set prefix the set index comes before ``key2``: it is
the page (``[section, set_index, key]``); with one, it is a block within the
page (``[section, page, key, set_index]``).

The entry is ``[option URI, text]`` (``option_text``), the item
``{ID, Name, Description}`` (``external_id``; the ID question of a page:
only its ID), or the value itself.
'''

from .core.values import basic_dict, basic_list

FLAGS = ('set_prefix', 'set_index', 'collection_index', 'external_id', 'option_text')
'''The flags of a question, in the order of :func:`flags`.'''

ALLOWED = frozenset({
    (False, False, False, False, False),
    (True, False, False, False, False),
    (False, True, False, False, False),
    (True, True, False, False, False),
    (False, True, True, False, False),
    (True, False, True, False, False),
    (True, True, True, False, False),
    (False, False, True, False, False),
    (False, False, True, True, False),
    (False, True, False, True, False),
    (True, True, False, True, False),
    (True, False, True, True, False),
    (True, True, True, True, False),
    (True, False, False, False, True),
    (True, True, False, False, True),
    (True, False, True, False, True),
    (False, True, True, False, True),
    (True, True, True, False, True),
})
'''The flag combinations the questions use (:func:`flags`); another one is an error in ``questions.json``.'''


def flags(config):
    '''The flags of the question *config* as a tuple in the order of :data:`FLAGS`.'''
    return tuple(bool(config.get(name)) for name in FLAGS)


def route(value, attribute, config, prefix_idx):
    '''The entry of *value* and its path in the answers dict.

    Args:
        value:      RDMO :class:`~rdmo.projects.models.Value` instance.
        attribute:  Attribute of *value* that holds it (``'option_uri'`` or ``'text'``).
        config:     Question config with ``key1``, ``key2``, ``key3`` and the flags.
        prefix_idx: The set prefix of *value* as a number (``None`` without one).

    Returns:
        Tuple ``(entry, path)``.

    Raises:
        ValueError: If the flags of *config* are not a combination of :data:`ALLOWED`.
    '''
    set_prefix, set_index, collection_index, external_id, option_text = combination = flags(config)
    if combination not in ALLOWED:
        raise ValueError(f"questions.json: {config.get('uri')} has the flags {combination}, "
                         f"which no rule handles")

    if option_text:
        entry = basic_list(value)
    elif external_id and set_index and not (set_prefix or collection_index):
        entry = value.external_id               # the ID question of a page
    elif external_id:
        entry = basic_dict(value)
    else:
        entry = getattr(value, attribute)

    path = [config['key1']]
    if set_prefix:
        path.append(prefix_idx)
    elif set_index:
        path.append(value.set_index)
    path.append(config['key2'])
    if set_prefix and set_index:
        path.append(value.set_index)
    if collection_index:
        path.append(value.collection_index)
    if config.get('key3'):
        path.append(config['key3'])
    return entry, path
