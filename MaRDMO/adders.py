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
- ``add_properties``         — write data-property values; drops mutually exclusive pairs
- ``add_references``         — write external-reference values; skips malformed QUDT IDs
'''

from rdmo.options.models import Option

from .constants import BASE_URI
from .getters import get_id, get_mathmoddb, get_options
from .helpers import (
    extract_parts,
    initialize_counter,
    process_qualifier,
    reduce_prefix,
    relation_exists,
    relevant_set_ids,
    value_editor,
)
from .model.constants import data_properties_check, qudt_reference_ids
from .patterns import QUDT_ID_STRICT_RE
from .workflow.models import ProcessStepUsage

def add_basics(project, text, questions, item_type, index = (None, None)):
    '''Parse the ID-question text and write label/description into the questionnaire.

    Splits *text* (format ``"Label (Description) [source]"``) and stores the
    label and description in the Name and Description answer fields of the
    entity page identified by *item_type*.

    Args:
        project:   RDMO project instance.
        text:      Human-readable ID string ``"Label (Description) [source]"``.
        questions: Questions dict for the relevant catalog.
        item_type: Entity type key in *questions* (e.g. ``"Research Field"``).
        index:     ``(set_index, set_prefix)`` tuple for the target page.

    Returns:
        Tuple ``(label, description, source)`` extracted from *text*.
    '''

    # Extract Label, Description, Source from ID Question
    label, description, source = extract_parts(text)

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

    return label, description, source

def add_entities(project, question_set, datas, source, prefix):
    '''Ensure each item in *datas* has a page in *question_set*, creating one if absent.

    Checks the existing questionnaire values (by external ID and by
    label/description) before adding a new set entry.  Skips items that are
    already present under any of those checks.

    Args:
        project:      RDMO project instance.
        question_set: Attribute URI of the set question (e.g. the section root).
        datas:        Iterable of :class:`~MaRDMO.models.Relatant` instances.
        source:       Source tag written into the ID field (e.g. ``"mardi"``).
        prefix:       Label prefix for the set page (e.g. ``"AD"``).
    '''

    # Generate ID, Name and Description URL from Set URL
    question = {'id': f'{question_set}/id',
                'name': f'{question_set}/name',
                'description': f'{question_set}/description'}

    # Get existing Set and Item Information
    info = {'set_ids': get_id(project, question_set, ['set_index']),
            'value_ids': get_id(project, question['id'], ['external_id']),
            'texts': get_id(project, question['id'], ['text']),
            'names': get_id(project, question['name'], ['text']),
            'descs': get_id(project, question['description'], ['text'])}

    # Add Item to Questionnaire
    idx = max(info['set_ids'], default = -1) + 1

    for data in datas:
        # Label Description String
        name_desc = f'{data.label} ({data.description})'
        # Check if Item already in Questionnaire via ID Question
        check_id = any(
            name_desc in text
            for text in info['texts']
            )
        # Check if Item already in Questionnaire via Name/Description Question
        check_name_desc = any(
            name_desc in f'{name} ({desc})'
            for name, desc in zip(info['names'], info['descs'])
            )
        # If Item not already in Questionnaire
        if data.id not in info['value_ids'] and not check_id and not check_name_desc:
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
                    'text': f'{data.label} ({data.description}) [{source}]',
                    'external_id': f"{data.id}",
                    'set_index': idx
                }
            )

            # Update Index and existing Items
            idx += 1
            info['value_ids'].append(data.id)

def add_new_entities(project, question_set, datas, prefix):
    '''Ensure each user-defined item in *datas* has a page in *question_set*.

    Like :func:`add_entities`, but for user-created items (no external ID).
    Deduplicates by label/description only and marks new entries with
    ``external_id = "not found"``.

    Args:
        project:      RDMO project instance.
        question_set: Attribute URI of the set question.
        datas:        Iterable of :class:`~MaRDMO.models.Relatant` instances.
        prefix:       Label prefix for the set page.
    '''

    # Generate ID, Name and Description URL from Set URL
    question = {'id': f'{question_set}/id',
                'name': f'{question_set}/name',
                'description': f'{question_set}/description'}

    # Get existing Set and Item Information
    info = {'set_ids': get_id(project, question_set, ['set_index']),
            'names': get_id(project, question['name'], ['text']),
            'descs': get_id(project, question['description'], ['text'])}

    # Add Publication to Questionnaire
    idx = max(info['set_ids'], default = -1) + 1
    for data in datas:
        # Label Description String
        name_desc = f'{data.label} ({data.description})'
        # Check if Item already in Questionnaire via Name/Description Question
        check_name_desc = any(
            name_desc == f'{name} ({desc})'
            for name, desc in zip(info['names'], info['descs'])
            )
        # If Item not already in Questionnaire
        if not check_name_desc:
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
                    'text': 'not found',
                    'external_id': 'not found',
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

            # Update Index
            idx += 1

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

    # Get existing Set and Item Information
    info = {'set_prefix_ids': get_id(project, statement['relatant'], ['set_prefix']),
            'set_index_ids': get_id(project, statement['relatant'], ['set_index']),
            'collection_ids': get_id(project, statement['relatant'], ['collection_index']),
            'value_ids': get_id(project, statement['relatant'], ['external_id']),
            'texts': get_id(project, statement['relatant'], ['text'])}

    # Get reduced set_prefixes
    index.update({'set_prefix_reduced': reduce_prefix(index['set_prefix'])})

    # Set initial value of counter
    index.update({'idx': initialize_counter(info['collection_ids'])})

    # Add Relations and Relatants
    for prop in props['keys']:
        inner_idx = 0
        for value in getattr(data, prop):
            assumption_index = None

            # Get Source and Label Description String
            source, _ = value.id.split(':')

            # Check if Relatant exists
            matches = relation_exists(
                value = value,
                set_prefix_red = index['set_prefix_reduced'],
                info = info)

            if matches:
                # Continue if existing
                continue

            # Add Assumption
            if statement.get('platform') and isinstance(value, ProcessStepUsage):
                index['idx'] += 1
                inner_idx = 0
                assumption_index = index['idx']

                if value.qualifier:
                    qual_source, _ = value.qualifier.split(':')
                    value_editor(
                        project = project,
                        uri = statement['platform'],
                        info = {
                            'text': f"{value.qualifier_label} ({value.qualifier_description}) [{qual_source}]",
                            'external_id': value.qualifier,
                            'collection_index': 0,
                            'set_index': assumption_index,
                            'set_prefix': index['set_prefix']
                        }
                    )

                if statement.get('hardware') and value.hardware:
                    hw_source, _ = value.hardware.split(':')
                    value_editor(
                        project = project,
                        uri = statement['hardware'],
                        info = {
                            'text': f"{value.hardware_label} ({value.hardware_description}) [{hw_source}]",
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
                    'text': f"{value.label} ({value.description}) [{source}]",
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
            info['texts'].append(f"{value.label} ({value.description}) [{source}]")

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
                   (:class:`~MaRDMO.helpers.PropertyRegistry` mapping prop
                   name → relation URL).
        index:     Dict containing ``'set_prefix'``; updated with
                   ``'set_prefix_reduced'`` and ``'idx'`` in place.
        statement: Dict with keys ``'relation'``, ``'relatant'``, and
                   optionally ``'assumption'`` (attribute URIs).
    '''

    # Get existing Set, Item and Relation Information
    info = {'set_prefix_ids': get_id(project, statement['relatant'], ['set_prefix']),
            'set_index_ids': get_id(project, statement['relatant'], ['set_index']),
            'collection_ids': get_id(project, statement['relatant'], ['collection_index']),
            'value_ids': get_id(project, statement['relatant'], ['external_id']),
            'texts': get_id(project, statement['relatant'], ['text']),
            'rels': get_id(project, statement['relation'], ['option_uri'])}

    # Get reduced set prefix ids
    index.update({'set_prefix_reduced': reduce_prefix(index['set_prefix'])})

    # Get relevant set index ids
    ids = relevant_set_ids(info, index['set_prefix_reduced'])

    # Set initial value of counter
    index.update({'idx': initialize_counter(ids)})

    # Add Relations and Relatants
    for prop in props['keys']:
        inner_idx = 0
        assumption_store = {}
        for value in getattr(data, prop):
            assumption_index = None
            # Get Source and Label Description String
            source, _ = value.id.split(':')

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
                    index['idx'] +=1
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
                            'text': "{label} ({description}) [{source}]".format_map(
                                assumption_value
                            ),
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
                    'set_index': assumption_index or index['idx'],
                    'set_prefix': index['set_prefix']
                }
            )

            # Add Relatant to Questionnaire
            value_editor(
                project = project,
                uri = statement['relatant'],
                info = {
                    'text': f"{value.label} ({value.description}) [{source}]",
                    'external_id': value.id,
                    'collection_index': inner_idx,
                    'set_index': assumption_index or index['idx'],
                    'set_prefix': index['set_prefix']
                }
            )

            # Update existing IDs, Texts, and Relations
            info['value_ids'].append(value.id)
            info['set_prefix_ids'].append(index['set_prefix_reduced'])
            info['texts'].append(f"{value.label} ({value.description}) [{source}]")
            info['rels'].append(props['mapping'].get(key=prop)["url"])

            inner_idx += 1

        # Update index
        index['idx'] += 1

def add_properties(project, data, uri, set_prefix):
    '''Write the data-property option values from *data.properties* into the questionnaire.

    Iterates over the ``{collection_index: [option_uri, …]}`` mapping in
    ``data.properties`` and calls :func:`~MaRDMO.helpers.value_editor` for
    each entry at ``set_index=0``.

    Entries whose option URI belongs to a mutually exclusive pair (as defined
    by ``data_properties_check``) are silently skipped — the entire conflicting
    pair is dropped because it cannot be determined which side is correct.  The
    documentation checker will report the missing properties at export time.

    Args:
        project:    RDMO project instance.
        data:       Dataclass instance with a ``properties`` attribute.
        uri:        Attribute URI of the data-property collection question.
        set_prefix: Set-prefix of the parent entity page.
    '''
    incoming_uris = {value[0] for value in data.properties.values()}
    mathmoddb = get_mathmoddb()
    conflict = set()
    for key_a, key_b in data_properties_check:
        entry_a = mathmoddb.get(key=key_a)
        entry_b = mathmoddb.get(key=key_b)
        if entry_a and entry_b:
            if entry_a['url'] in incoming_uris and entry_b['url'] in incoming_uris:
                conflict.add(entry_a['url'])
                conflict.add(entry_b['url'])

    for key, value in data.properties.items():
        if value[0] in conflict:
            continue
        value_editor(
            project = project,
            uri  = uri,
            info = {
                'option': Option.objects.get(uri=value[0]),
                'collection_index': key,
                'set_index': 0,
                'set_prefix': set_prefix
            }
        )

def add_references(project, data, uri, set_index = 0, set_prefix = None):
    '''Write the reference entries from *data.reference* into the questionnaire.

    Does nothing when ``data.reference`` is empty.  Each entry in the
    ``{collection_index: [option_uri, text]}`` mapping is stored as an option
    value at the given *set_index* / *set_prefix*.

    For QUDT reference options (quantity kind ID or constant ID), the text is
    validated against ``^[A-Z][a-zA-Z_\\-]+$`` and silently skipped when it
    does not match.  The documentation checker will report the missing reference
    at export time.

    Args:
        project:    RDMO project instance.
        data:       Dataclass instance with a ``reference`` attribute.
        uri:        Attribute URI of the reference collection question.
        set_index:  Set-index of the parent entity page (default ``0``).
        set_prefix: Set-prefix of the parent entity page (optional).
    '''
    if not data.reference:
        return

    options = get_options()
    qudt_option_uris = {options[k] for k in qudt_reference_ids if k in options}

    for key, value in data.reference.items():
        option_uri, text = value[0], value[1]
        if option_uri in qudt_option_uris and not QUDT_ID_STRICT_RE.match(text or ''):
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
