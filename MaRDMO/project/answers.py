'''The answers of a project, read from the RDMO database.

:func:`get_answers` reads the values of one question into the answers dict
(where they go: :func:`~MaRDMO.rules.route`), :func:`process_question_dict`
does so for every question of a catalog, and :func:`get_id` reads fields of
the values of one attribute.
'''
from rdmo.domain.models import Attribute

from ..core.constants import BASE_URI
from ..rules import route
from ..core.values import nested_set
from ..writes import get_attribute


def get_id(project, uri, keys):
    '''Retrieve one or more attribute fields from all questionnaire values at *uri*.

    Args:
        project: RDMO project instance.
        uri:     Full RDMO attribute URI to filter on.
        keys:    List of :class:`~rdmo.projects.models.Value` field names to
                 read (e.g. ``["set_index"]``, ``["external_id"]``, or
                 ``["set_index", "set_prefix"]``).  When *keys* has exactly
                 one element, multi-value pipe-separated strings are split and
                 only the first part is returned.

    Returns:
        List of scalar values (single-key case) or list of lists (multi-key
        case), one entry per matching questionnaire value.
    '''
    values = project.values.filter(
        snapshot=None,
        attribute=get_attribute(uri)
    )
    identifiers = []
    if len(keys) == 1:
        for value in values:
            identifier = getattr(value, keys[0])
            if isinstance(identifier, str) and '|' in identifier:
                identifier = identifier.split('|')[0]
            identifiers.append(identifier)
    else:
        for value in values:
            identifier = []
            for key in keys:
                identifier.append(getattr(value, key))
            identifiers.append(identifier)
    return identifiers

def get_answers(project, val, config):
    '''Read questionnaire values for one attribute and merge them into *val*.

    Iterates over all :class:`~rdmo.projects.models.Value` objects for the
    attribute described by *config*, determines the appropriate path in *val*
    with :func:`~.rules.route`, and calls
    :func:`~MaRDMO.core.values.nested_set` to write the entry.

    Args:
        project: RDMO project instance.
        val:     Top-level answers dict that is mutated in place.
        config:  Dict describing how to map a questionnaire attribute to *val*:

                 * ``"uri"``              – RDMO attribute URI fragment
                 * ``"key1"``             – top-level key in *val*
                 * ``"key2"``             – second-level key (may be empty)
                 * ``"set_prefix"``       – bool flag: use set_prefix as path element
                 * ``"set_index"``        – bool flag: use set_index as path element
                 * ``"collection_index"`` – bool flag: use collection_index
                 * ``"external_id"``      – bool flag: write external_id field
                 * ``"option_text"``      – bool flag: write option URI as text

    Returns:
        The mutated *val* dict.
    '''

    val.setdefault(config["key1"], {})

    try:
        values = project.values.filter(
            snapshot=None,
            attribute=Attribute.objects.get(uri = f"{BASE_URI}{config['uri']}")
            )
    except Attribute.DoesNotExist:
        values = []

    if not (config["key1"] or config["key2"]):
        return val

    for value in values:

        # Set Prefix IDX
        prefix_idx = None
        if value.set_prefix:
            prefix_idx = int(value.set_prefix.split('|')[0])

        # Set Attribute
        attribute = 'option_uri' if value.option else 'text' if value.text else None

        if not attribute:
            # Ignore if not Attribute Set
            continue

        # Get Entry and Path
        entry, path = route(value, attribute, config, prefix_idx)

        # Generate nested Dict Entry
        nested_set(data=val,
                   path=path,
                   entry=entry)

    return val


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
