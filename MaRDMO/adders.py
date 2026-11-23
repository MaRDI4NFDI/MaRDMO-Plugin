'''Functions that write retrieved metadata into an RDMO questionnaire.

After a background worker has collected entity data from external knowledge
graphs, the results must be stored as RDMO ``Value`` objects so that the
questionnaire reflects the fetched information.  This module provides helpers
that create or update those values for a given project and set of answers.

Portal-fetched data is sanitized before writing: ``add_properties`` silently
drops any pair of mutually exclusive data properties (neither can be judged
correct), and ``add_references`` skips QUDT IDs that do not match the expected
format.  The documentation checker surfaces any resulting gaps at export time.

Provides:

- ``add_basics``             — write basic (label/description) values for a single entity entry
- ``add_entities``           — write a list of entities into a set of questionnaire answers
- ``add_new_entities``       — write newly user-created entities into the questionnaire
- ``add_relations_static``   — write relation values using a fixed property-to-question mapping
- ``add_relations_flexible`` — write relation values using a dynamic property-to-question mapping
- ``add_references``         — write external-reference values; skips those in a wrong format
'''


from rdmo.options.models import Option

from .core.constants import BASE_URI
from .core.config import get_options
from .project.answers import get_id
from .core.values import extract_parts, process_qualifier
from .writes import value_editor
from .core.ids import NEW_ITEM, item_text
from .core.models import Usage

def add_basics(project, text, questions, item_type, index = (None, None)):
    '''Parse the ID-question text and write label/description into the questionnaire.

    Splits *text* (format ``"Label (Description)"``) and stores the
    label and description in the Name and Description answer fields of the
    entity page identified by *item_type*.

    Args:
        project:   RDMO project instance.
        text:      Human-readable ID string ``"Label (Description)"``.
        questions: Questions dict for the relevant catalog.
        item_type: Entity type key in *questions* (e.g. ``"Research Field"``).
        index:     ``(set_index, set_prefix)`` tuple for the target page.

    '''

    # Extract Label and Description from ID Question
    label, description, _ = extract_parts(text)

    # Add Label to Questionnaire
    value_editor(
        project = project,
        uri = f'{BASE_URI}{questions[item_type]["Name"]["uri"]}',
        info = {
            'text': label,
            'set_index': index[0],
            'set_prefix': index[1]
        }
    )

    # Add Description to Questionnaire
    value_editor(
        project = project,
        uri = f'{BASE_URI}{questions[item_type]["Description"]["uri"]}',
        info = {
            'text': description,
            'set_index': index[0],
            'set_prefix': index[1]
        }
    )

def _first_part(text):
    '''*text* up to its first ``|`` (as :func:`~MaRDMO.project.answers.get_id` reads a single field).'''
    return text.split('|')[0] if isinstance(text, str) and '|' in text else text


def add_entities(project, question_set, datas, prefix):
    '''Ensure each item in *datas* has a page in *question_set*, creating one if absent.

    An item has a page when a page has its ID; an own page with the same
    label and description is another item.

    Args:
        project:      RDMO project instance.
        question_set: Attribute URI of the set question (e.g. the section root).
        datas:        Iterable of :class:`~MaRDMO.core.models.Relatant` instances.
        prefix:       Label prefix for the set page (e.g. ``"AD"``).
    '''

    # Generate ID URL from Set URL
    question = {'id': f'{question_set}/id'}

    # Get existing Set and Item Information
    info = {'set_ids': get_id(project, question_set, ['set_index']),
            'value_ids': get_id(project, question['id'], ['external_id'])}

    # Add Item to Questionnaire
    idx = max(info['set_ids'], default = -1) + 1

    for data in datas:
        # If Item not already in Questionnaire
        if data.id not in info['value_ids']:
            # Set up Page in Questionnaire
            value_editor(
                project = project,
                uri = question_set,
                info = {
                    'text': f"{prefix}{int(idx)+1}",
                    'set_index': idx
                }
            )
            # Add ID Values
            value_editor(
                project = project,
                uri = question['id'],
                info = {
                    'text': item_text(data.label, data.description),
                    'external_id': f"{data.id}",
                    'set_index': idx
                }
            )

            # Update Index and existing Items
            idx += 1
            info['value_ids'].append(data.id)

def add_new_entities(project, question_set, datas, prefix):
    '''Ensure each new item of the user's own in *datas* has a page in *question_set*.

    Like :func:`add_entities`, but for items the user creates in a relation
    ("new" option): the page gets the ``user:`` ID the relation holds, so the
    relation refers to it.  A page with that ID already there is kept; pages
    are never matched by name (another item may have the same name).

    Args:
        project:      RDMO project instance.
        question_set: Attribute URI of the set question.
        datas:        Iterable of :class:`~MaRDMO.core.models.Relatant` instances
                      (``id`` is the ``user:`` ID).
        prefix:       Label prefix for the set page.
    '''

    # Generate ID, Name and Description URL from Set URL
    question = {'id': f'{question_set}/id',
                'name': f'{question_set}/name',
                'description': f'{question_set}/description'}

    # Get existing Set and Item Information
    info = {'set_ids': get_id(project, question_set, ['set_index']),
            'value_ids': get_id(project, question['id'], ['external_id'])}

    idx = max(info['set_ids'], default = -1) + 1
    for data in datas:
        if data.id in info['value_ids']:
            continue
        # Set up Page
        value_editor(
            project = project,
            uri = question_set,
            info = {
                'text': f"{prefix}{int(idx)+1}",
                'set_index': idx
            }
        )
        # Add ID Values
        value_editor(
            project = project,
            uri = question['id'],
            info = {
                'text': NEW_ITEM,
                'external_id': data.id,
                'set_index': idx
            }
        )
        # Add Name Values
        value_editor(
            project = project,
            uri = question['name'],
            info = {
                'text': data.label,
                'set_prefix': idx
            }
        )
        # Add Description Values
        value_editor(
            project = project,
            uri = question['description'],
            info = {
                'text': data.description,
                'set_prefix': idx
            }
        )

        # Update Index and existing Items
        idx += 1
        info['value_ids'].append(data.id)

def add_relations_static(project, data, props, index, statement):
    '''Write static (fixed-type) relations from *data* into the questionnaire.

    Iterates over the relatant lists named by ``props['keys']`` and, for each
    relatant not already present (checked by external ID and text), adds a
    new collection entry to ``statement['relatant']``.

    When ``statement`` contains a ``'platform'`` key and a relatant carries a
    ``qualifier`` attribute, platform values are written first and the relatant
    is grouped under the corresponding platform set-index with ``inner_idx``
    as its collection-index.  The grouping key is ``(qualifier, other)`` so
    that two relatants with the same platform but different ``other`` payloads
    land in separate sets.  When ``statement`` also contains a ``'parameter'``
    key and the relatant has a non-empty ``other`` field, each ``' || '``-split
    segment of ``other`` is written as a separate parameter entry.
    Without a qualifier the original behaviour is preserved:
    ``set_index=0``, ``collection_index=index['idx']``.

    Args:
        project:   RDMO project instance.
        data:      Dataclass instance whose attributes hold lists of relatants.
        props:     Dict with key ``'keys'`` listing attribute names on *data*.
        index:     Dict containing ``'set_prefix'``; ``'set_prefix_reduced'``
                   and ``'idx'`` are computed and written back into this dict.
        statement: Dict with key ``'relatant'`` (attribute URI of the
                   collection question) and optional keys ``'platform'``
                   (attribute URI of the platform question) and
                   ``'parameter'`` (attribute URI of the parameter question).
    '''

    # Get existing Set and Item Information (one query)
    relatants = get_id(project, statement['relatant'], ['set_prefix', 'set_index', 'collection_index', 'external_id'])
    info = {'set_prefix_ids': [_first_part(set_prefix) for set_prefix, _, _, _ in relatants],
            'value_ids': [_first_part(external_id) for _, _, _, external_id in relatants]}

    # Get reduced set_prefixes
    index.update({'set_prefix_reduced': reduce_prefix(index['set_prefix'])})

    # Count only within the sets of this entity: without platform all relatants
    # share set 0 and idx is the collection index, with platform each relatant
    # gets a set of its own (numbered from 1) and idx is the set index
    own = [(set_index, collection_index) for set_prefix, set_index, collection_index, _ in relatants
           if str(set_prefix) == str(index['set_prefix'])]
    if statement.get('platform'):
        index.update({'idx': max((set_index for set_index, _ in own), default=0)})
    else:
        index.update({'idx': initialize_counter(
            [collection_index for set_index, collection_index in own if set_index == 0])})

    # Add Relations and Relatants
    for prop in props['keys']:
        inner_idx = 0
        for value in getattr(data, prop):
            assumption_index = None

            # Check if Relatant exists
            matches = relation_exists(
                value = value,
                set_prefix_red = index['set_prefix_reduced'],
                info = info)

            if matches:
                # Continue if existing
                continue

            # Add Assumption
            if statement.get('platform') and isinstance(value, Usage):
                index['idx'] += 1
                inner_idx = 0
                assumption_index = index['idx']

                if value.qualifier:
                    value_editor(
                        project = project,
                        uri = statement['platform'],
                        info = {
                            'text': item_text(value.qualifier_label, value.qualifier_description),
                            'external_id': value.qualifier,
                            'collection_index': 0,
                            'set_index': assumption_index,
                            'set_prefix': index['set_prefix']
                        }
                    )

                if statement.get('hardware') and value.hardware:
                    value_editor(
                        project = project,
                        uri = statement['hardware'],
                        info = {
                            'text': item_text(value.hardware_label, value.hardware_description),
                            'external_id': value.hardware,
                            'collection_index': 0,
                            'set_index': assumption_index,
                            'set_prefix': index['set_prefix']
                        }
                    )

                if statement.get('documentation'):
                    doc_idx = 0
                    for doc_val in (value.doi, value.url):
                        if doc_val:
                            value_editor(
                                project = project,
                                uri = statement['documentation'],
                                info = {
                                    'text': doc_val[1],
                                    'option': Option.objects.get(uri=doc_val[0]),
                                    'collection_index': doc_idx,
                                    'set_index': assumption_index,
                                    'set_prefix': index['set_prefix']
                                }
                            )
                            doc_idx += 1

                if statement.get('parameter') and value.parameters:
                    for i, param in enumerate(value.parameters.split(' || ')):
                        value_editor(
                            project = project,
                            uri = statement['parameter'],
                            info = {
                                'text': param,
                                'collection_index': i,
                                'set_index': assumption_index,
                                'set_prefix': index['set_prefix']
                            }
                        )

            # Add Relatant to Questionnaire
            value_editor(
                project = project,
                uri = statement['relatant'],
                info = {
                    'text': item_text(value.label, value.description),
                    'external_id': value.id,
                    'collection_index': inner_idx if assumption_index is not None else index['idx'],
                    'set_index': assumption_index or 0,
                    'set_prefix': index['set_prefix']
                }
            )

            # Update Index
            if assumption_index is not None:
                inner_idx += 1
            else:
                index['idx'] += 1

            # Update existing IDs, Texts, and Relations
            info['value_ids'].append(value.id)
            info['set_prefix_ids'].append(index['set_prefix_reduced'])

def add_relations_flexible(project, data, props, index, statement):
    '''Write flexible (typed) relations from *data* into the questionnaire.

    For each relatant in ``data.<prop>`` (where *prop* ∈ ``props['keys']``),
    checks whether the (relation-type, relatant) pair already exists.  If not,
    writes the relation-type option and the relatant text/ID, handling the
    optional assumption qualifier.

    Args:
        project:   RDMO project instance.
        data:      Dataclass instance whose attributes hold lists of relatants.
        props:     Dict with keys ``'keys'`` (attribute names) and ``'mapping'``
                   (:class:`~MaRDMO.core.properties.PropertyRegistry` mapping prop
                   name → relation URL).
        index:     Dict containing ``'set_prefix'``; updated with
                   ``'set_prefix_reduced'`` and ``'idx'`` in place.
        statement: Dict with keys ``'relation'``, ``'relatant'``, and
                   optionally ``'assumption'`` (attribute URIs).
    '''

    # Get existing Set, Item and Relation Information; 'rels' holds the
    # relation of each relatant's set (a set has one relation, several relatants)
    relation_of_set = {
        (set_prefix, set_index): option_uri
        for set_prefix, set_index, option_uri in get_id(
            project, statement['relation'], ['set_prefix', 'set_index', 'option_uri'])
    }
    relatants = get_id(project, statement['relatant'], ['set_prefix', 'set_index', 'external_id'])
    info = {'set_prefix_ids': [_first_part(set_prefix) for set_prefix, _, _ in relatants],
            'set_index_ids': [set_index for _, set_index, _ in relatants],
            'value_ids': [_first_part(external_id) for _, _, external_id in relatants],
            'rels': [relation_of_set.get((set_prefix, set_index)) for set_prefix, set_index, _ in relatants]}

    # Get reduced set prefix ids
    index.update({'set_prefix_reduced': reduce_prefix(index['set_prefix'])})

    # Get relevant set index ids (also of sets with a relation but no relatant yet)
    ids = relevant_set_ids(info, index['set_prefix_reduced']) + relevant_set_ids(
        {'set_index_ids': [set_index for _, set_index in relation_of_set],
         'set_prefix_ids': [set_prefix for set_prefix, _ in relation_of_set]},
        index['set_prefix_reduced'])

    # Set initial value of counter
    index.update({'idx': initialize_counter(ids)})

    # Relatants without an assumption share one set, each assumption gets a set
    # of its own; group them first, as the portal returns them in no fixed order
    def assumption_group(value):
        qualifier = getattr(value, 'qualifier', None) if statement.get('assumption') else None
        return (bool(qualifier), qualifier or '')

    # Add Relations and Relatants; a set number is only used up once something
    # is written into it, so the sets are numbered without gaps
    for prop in props['keys']:
        inner_idx = 0
        assumption_store = {}
        used = False
        for value in sorted(getattr(data, prop), key=assumption_group):
            assumption_index = None

            # Check if Relation / Relatant Combination exists (flexible relation)
            matches = relation_exists(
                value = value,
                set_prefix_red = index['set_prefix_reduced'],
                info = info,
                relation_id = props['mapping'].get(key=prop)["url"]
            )

            if matches:
                # Continue if existing
                continue

            # Add Assumption
            if statement.get('assumption') and hasattr(value, 'qualifier') and value.qualifier:
                if value.qualifier not in assumption_store:
                    if used:
                        index['idx'] += 1
                    inner_idx = 0
                    assumption_store.update({value.qualifier: index['idx']})
                assumption_index = assumption_store.get(value.qualifier)
                # Get Assumptions
                assumption_dict = process_qualifier(value.qualifier)
                # Add Assumptions
                for assumption_key, assumption_value in assumption_dict.items():
                    value_editor(
                        project = project,
                        uri = statement['assumption'],
                        info = {
                            'text': item_text(assumption_value['label'], assumption_value['description']),
                            'external_id': assumption_value['id'],
                            'collection_index': assumption_key,
                            'set_index': assumption_index,
                            'set_prefix': index['set_prefix']
                        }
                    )

            # Add Relation to Questionnaire
            value_editor(
                project = project,
                uri = statement['relation'],
                info = {
                    'option': Option.objects.get(uri=props['mapping'].get(key=prop)["url"]),
                    'collection_index': None,
                    'set_index': index['idx'] if assumption_index is None else assumption_index,
                    'set_prefix': index['set_prefix']
                }
            )

            # Add Relatant to Questionnaire
            value_editor(
                project = project,
                uri = statement['relatant'],
                info = {
                    'text': item_text(value.label, value.description),
                    'external_id': value.id,
                    'collection_index': inner_idx,
                    'set_index': index['idx'] if assumption_index is None else assumption_index,
                    'set_prefix': index['set_prefix']
                }
            )

            # Update existing IDs, Texts, and Relations
            info['value_ids'].append(value.id)
            info['set_prefix_ids'].append(index['set_prefix_reduced'])
            info['rels'].append(props['mapping'].get(key=prop)["url"])

            inner_idx += 1
            used = True

        # Update index
        if used:
            index['idx'] += 1

def add_references(project, data, uri, set_index = 0, set_prefix = None, formats=None):
    '''Write the reference entries from *data.reference* into the questionnaire.

    Does nothing when ``data.reference`` is empty.  Each entry in the
    ``{collection_index: [option_uri, text]}`` mapping is stored as an option
    value at the given *set_index* / *set_prefix*.

    A reference of an option in *formats* whose text does not match its
    pattern is silently skipped (e.g. the QUDT IDs of a quantity, see
    ``model/handlers.py``).  The documentation checker will report the
    missing reference at export time.

    Args:
        project:    RDMO project instance.
        data:       Dataclass instance with a ``reference`` attribute.
        uri:        Attribute URI of the reference collection question.
        set_index:  Set-index of the parent entity page (default ``0``).
        set_prefix: Set-prefix of the parent entity page (optional).
        formats:    ``{option key: compiled pattern}`` the text of a reference
                    of that option must match (optional).
    '''
    if not data.reference:
        return

    options = get_options()
    patterns = {options[key]: pattern for key, pattern in (formats or {}).items() if key in options}

    for key, value in data.reference.items():
        option_uri, text = value[0], value[1]
        if option_uri in patterns and not patterns[option_uri].match(text or ''):
            continue
        value_editor(
            project = project,
            uri  = uri,
            info = {
                'text': text,
                'option': Option.objects.get(uri=option_uri),
                'collection_index': key,
                'set_index': set_index,
                'set_prefix': set_prefix
            }
        )


def initialize_counter(counter):
    '''Return ``max(counter) + 1``, or ``0`` when *counter* is empty.

    Args:
        counter: Iterable of numeric values (e.g. existing set-index list).

    Returns:
        Next available integer index.
    '''
    return int(max(counter, default=-1)) + 1


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

    A relation is the same when it has the item's ID (#103); another item
    with the same label and description is another relation.

    Args:
        value:           Relatant object with an ``id`` attribute.
        set_prefix_red:  Reduced integer set-prefix of the parent entity.
        info:            Dict of existing DB values keyed by ``value_ids``,
                         ``set_prefix_ids``, and optionally ``rels``.
        relation_id:     Option URI of the relation type; when provided the
                         check also verifies that the relation type matches.

    Returns:
        ``True`` if the combination is already present, ``False`` otherwise.
    '''

    # Case: relation check required
    if relation_id and "rels" in info:
        return any(
            vid == value.id and int(sid) == set_prefix_red and rel == relation_id
            for vid, sid, rel in zip(info['value_ids'], info['set_prefix_ids'], info['rels'])
        )

    # Case: only value + set check
    return any(
        vid == value.id and int(sid) == set_prefix_red
        for vid, sid in zip(info['value_ids'], info['set_prefix_ids'])
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
        # Stored prefixes are strings ('3'), written ones integers
        if set_prefix not in (None, '') and reduce_prefix(set_prefix) == set_prefix_red:
            relevant_set_ids_list.append(set_index)
    return relevant_set_ids_list
