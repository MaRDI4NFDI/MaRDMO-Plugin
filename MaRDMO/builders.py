'''The handlers and validators of the questions, by attribute URI, for the router.

The router (``router.py``) calls a handler after a value of a question is
saved or deleted, and a validator before it is saved.  This module builds
the maps ``{catalog name: {attribute URI: handler or validator}}`` once at
startup from the tables below, which name the questions by
``(question set, question)`` of the catalog's ``questions.json``.

The tables are keyed by question set (``model``, ``algorithm``,
``workflow``); a catalog gets the maps of its question set
(:attr:`~MaRDMO.catalogs.Catalog.questions`), so the model basics catalog
those of the model catalog: it has part of its questions, with the same
handlers and validators.  Every catalog also gets the publication's.

Provides:

- ``build_post_save_handler_set``   — post-save dispatch dict (all catalogs)
- ``build_post_delete_handler_set`` — post-delete dispatch dict (all catalogs)
- ``build_presave_validator_map``   — pre-save validation dispatch dict
'''

from .catalogs import CATALOGS, DOCUMENTING
from .constants import BASE_URI
from .getters import get_questions
from .model.handlers import Information as ModelInformation
from .algorithm.handlers import Information as AlgorithmInformation
from .workflow.handlers import Information as WorkflowInformation
from .publication.handlers import Information as PublicationInformation
from .handlers import Information as GeneralInformation
from .validators import (
    validate_archive_year,
    validate_count,
    validate_data_size,
    validate_doi,
    validate_properties,
    validate_publication_id,
    validate_qudt_id,
    validate_reference,
    validate_short_description,
    validate_single_line,
)

INFORMATION = {
    'model': ModelInformation,
    'algorithm': AlgorithmInformation,
    'workflow': WorkflowInformation,
}
'''The handler class of each question set.'''

HANDLERS = {
    'model': {
        ('Research Field', 'ID'): 'field',
        ('Research Problem', 'ID'): 'problem',
        ('Quantity', 'ID'): 'quantity',
        ('Mathematical Formulation', 'ID'): 'formulation',
        ('Task', 'ID'): 'task',
        ('Mathematical Model', 'ID'): 'model',
    },
    'algorithm': {
        ('Benchmark', 'ID'): 'benchmark',
        ('Software', 'ID'): 'software',
        ('Problem', 'ID'): 'problem',
        ('Algorithm', 'ID'): 'algorithm',
    },
    'workflow': {
        ('Workflow', 'ID'): 'workflow',
        ('Algorithm', 'ID'): 'algorithm',
        ('Workflow', 'Model'): 'model',
        ('Software', 'ID'): 'software',
        ('Hardware', 'ID'): 'hardware',
        ('Hardware', 'CPU'): 'processor_cores',
        ('Data Set', 'ID'): 'data_set',
        ('Process Step', 'ID'): 'process_step',
    },
}
'''The questions with a handler of their question set's class: ``{(question set, question): method}``.'''

RELATIONS = {
    'model': [
        ('Task', 'QRelatant'),
        ('Task', 'MFRelatant'),
        ('Mathematical Formulation', 'Element Quantity'),
        ('Quantity', 'Element Quantity'),
        ('Mathematical Model', 'MFRelatant'),
        ('Mathematical Model', 'Assumption'),
        ('Task', 'Assumption'),
        ('Mathematical Formulation', 'Assumption'),
        ('Mathematical Formulation', 'MFRelatant'),
        ('Research Problem', 'RFRelatant'),
        ('Mathematical Model', 'RPRelatant'),
        ('Mathematical Model', 'TRelatant'),
    ],
    'algorithm': [
        ('Problem', 'BRelatant'),
        ('Software', 'BRelatant'),
        ('Algorithm', 'PRelatant'),
        ('Algorithm', 'SRelatant'),
        ('Software', 'Dependency'),
    ],
    'workflow': [
        ('Process Step', 'Algorithm'),
        ('Process Step', 'Hardware'),
        ('Process Step', 'Input'),
        ('Process Step', 'Output'),
        ('Workflow', 'PSRelatant'),
        ('Process Step', 'Software'),
        ('Algorithm', 'SRelatant'),
        ('Software', 'Dependency'),
    ],
}
'''The relation questions: the general handler (:meth:`~MaRDMO.handlers.Information.relation`) fetches the item.'''

VALIDATORS = {
    'model': {
        validate_short_description: [
            ('Research Field', 'Description'),
            ('Research Problem', 'Description'),
            ('Quantity', 'Description'),
            ('Mathematical Formulation', 'Description'),
            ('Task', 'Description'),
            ('Mathematical Model', 'Description'),
        ],
        validate_single_line: [
            ('Research Field', 'Long Description'),
            ('Research Problem', 'Long Description'),
            ('Quantity', 'Long Description'),
            ('Mathematical Formulation', 'Long Description'),
            ('Task', 'Long Description'),
            ('Mathematical Model', 'Long Description'),
            ('Mathematical Formulation', 'Reference'),
        ],
        validate_properties: [
            ('Mathematical Model', 'Properties'),
            ('Mathematical Formulation', 'Properties'),
            ('Quantity', 'Properties'),
            ('Task', 'Properties'),
        ],
        validate_qudt_id: [
            ('Quantity', 'Reference'),
        ],
    },
    'algorithm': {
        validate_short_description: [
            ('Algorithm', 'Description'),
            ('Problem', 'Description'),
            ('Software', 'Description'),
            ('Benchmark', 'Description'),
        ],
        validate_reference: [
            ('Software', 'Reference'),
            ('Benchmark', 'Reference'),
        ],
    },
    'workflow': {
        validate_short_description: [
            ('Workflow', 'Description'),
            ('Algorithm', 'Description'),
            ('Software', 'Description'),
            ('Hardware', 'Description'),
            ('Data Set', 'Description'),
            ('Process Step', 'Description'),
        ],
        validate_single_line: [
            ('Workflow', 'Long Description'),
            ('Workflow', 'Mathematical'),
            ('Workflow', 'Runtime'),
            ('Workflow', 'Result'),
            ('Workflow', 'Original Platform'),
            ('Workflow', 'Other Platform'),
        ],
        validate_reference: [
            ('Software', 'Reference'),
            ('Process Step', 'Software-Documentation'),
            ('Process Step', 'Method-Documentation'),
        ],
        validate_doi: [
            ('Data Set', 'To Publish'),
        ],
        validate_archive_year: [
            ('Data Set', 'To Archive'),
        ],
        validate_data_size: [
            ('Data Set', 'Size'),
        ],
        validate_count: [
            ('Hardware', 'Nodes'),
            ('Hardware', 'Number of CPU'),
            ('Hardware', 'Cores'),
        ],
    },
}
'''The validators of the questions of each question set: ``{validator: [(question set, question), …]}``.

The publication ID of every catalog is checked by
:func:`~MaRDMO.validators.validate_publication_id` (#158).
'''


def _uri(questions, question_set, question):
    '''The attribute URI of *question* in *question_set* of *questions* (``questions.json``).'''
    return f'{BASE_URI}{questions[question_set][question]["uri"]}'


def _per_catalog(maps):
    '''``{catalog name: map}`` from ``{question set: map}``: each catalog the map of its question set.'''
    return {name: dict(maps[CATALOGS[name].questions]) for name in DOCUMENTING}


def build_post_save_handler_set():
    """Build the post-save map ``{catalog name: {attribute URI: handler}}``.

    The handlers of :data:`HANDLERS`, the general relation handler for
    :data:`RELATIONS`, and the publication's citation lookup for the
    publication ID, per catalog.  The router dispatches the
    ``value_created`` / ``value_updated`` signals with it.
    """
    publication = PublicationInformation()
    general = GeneralInformation()
    citation = _uri(get_questions('publication'), 'Publication', 'ID')
    maps = {}
    for key, information_class in INFORMATION.items():
        questions = get_questions(key)
        information = information_class()
        handlers = {_uri(questions, *question): getattr(information, method)
                    for question, method in HANDLERS[key].items()}
        handlers.update({_uri(questions, *question): general.relation for question in RELATIONS[key]})
        handlers[citation] = publication.citation
        maps[key] = handlers
    return _per_catalog(maps)


def build_post_delete_handler_set():
    """Build the post-delete map ``{catalog name: {attribute URI: handler}}``.

    When a publication page is deleted, its citation values are cleaned up
    (:meth:`~MaRDMO.publication.handlers.Information.publication_delete`);
    every documenting catalog has publications.
    """
    publication = PublicationInformation()
    pub_set_uri = f"{BASE_URI}{get_questions('publication')['Publication']['uri']}"
    return {name: {pub_set_uri: publication.publication_delete} for name in DOCUMENTING}


def build_presave_validator_map():
    """Build the pre-save map ``{catalog name: {attribute URI: validator}}`` from :data:`VALIDATORS`.

    Each attribute URI has one validator per catalog; a question that needs
    several combines them in one function (as
    :func:`~MaRDMO.validators.validate_reference` does).
    """
    publication_id = _uri(get_questions('publication'), 'Publication', 'ID')
    maps = {}
    for key, validators in VALIDATORS.items():
        questions = get_questions(key)
        maps[key] = {_uri(questions, *question): validator
                     for validator, found in validators.items() for question in found}
        maps[key][publication_id] = validate_publication_id
    return _per_catalog(maps)
