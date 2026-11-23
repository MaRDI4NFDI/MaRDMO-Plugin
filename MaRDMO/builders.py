'''The handlers and validators of the questions, by attribute URI, for the router.

The router (``router.py``) calls a handler after a value of a question is
saved or deleted, and a validator before it is saved.  This module builds
the maps ``{catalog name: {attribute URI: handler or validator}}`` once at
startup from the declarations of the catalogs (``catalog.py``,
:class:`~MaRDMO.core.catalogs.Registration`), which name the questions by
``(question set, question)`` of their ``questions.json``.

A catalog gets the maps of its question set
(:attr:`~MaRDMO.core.catalogs.Catalog.questions`), so the model basics catalog
those of the model catalog: it has part of its questions, with the same
handlers and validators.  Every catalog also gets the publication's.

Provides:

- ``build_post_save_handler_set``   — post-save dispatch dict (all catalogs)
- ``build_post_delete_handler_set`` — post-delete dispatch dict (all catalogs)
- ``build_presave_validator_map``   — pre-save validation dispatch dict
'''

from .core.catalogs import catalogs, documenting, registrations
from .core.constants import BASE_URI
from .core.config import get_questions
from .publication.handlers import Information as PublicationInformation
from .handlers import Information as GeneralInformation
from .validators import validate_publication_id


def _uri(questions, question_set, question):
    '''The attribute URI of *question* in *question_set* of *questions* (``questions.json``).'''
    return f'{BASE_URI}{questions[question_set][question]["uri"]}'


def _per_catalog(maps):
    '''``{catalog name: map}`` from ``{question set: map}``: each catalog the map of its question set.'''
    return {name: dict(maps[catalogs()[name].questions]) for name in documenting()}


def build_post_save_handler_set():
    """Build the post-save map ``{catalog name: {attribute URI: handler}}``.

    The handlers of the declarations (``handlers``), the general relation
    handler for their ``relations``, and the publication's citation lookup for
    the publication ID, per catalog.  The router dispatches the
    ``value_created`` / ``value_updated`` signals with it.
    """
    publication = PublicationInformation()
    general = GeneralInformation()
    citation = _uri(get_questions('publication'), 'Publication', 'ID')
    maps = {}
    for registration in registrations():
        if not registration.information:
            continue
        questions = get_questions(registration.question_set)
        information = registration.information_class()
        handlers = {_uri(questions, *question): getattr(information, method)
                    for question, method in registration.handlers.items()}
        handlers.update({_uri(questions, *question): general.relation for question in registration.relations})
        handlers[citation] = publication.citation
        maps[registration.question_set] = handlers
    return _per_catalog(maps)


def build_post_delete_handler_set():
    """Build the post-delete map ``{catalog name: {attribute URI: handler}}``.

    When a publication page is deleted, its citation values are cleaned up
    (:meth:`~MaRDMO.publication.handlers.Information.publication_delete`);
    every documenting catalog has publications.
    """
    publication = PublicationInformation()
    pub_set_uri = f"{BASE_URI}{get_questions('publication')['Publication']['uri']}"
    return {name: {pub_set_uri: publication.publication_delete} for name in documenting()}


def build_presave_validator_map():
    """Build the pre-save map ``{catalog name: {attribute URI: validator}}`` from the declarations.

    Each attribute URI has one validator per catalog; a question that needs
    several combines them in one function (as
    :func:`~MaRDMO.validators.validate_reference` does).
    """
    publication_id = _uri(get_questions('publication'), 'Publication', 'ID')
    maps = {}
    for registration in registrations():
        if not registration.information:
            continue
        questions = get_questions(registration.question_set)
        maps[registration.question_set] = {_uri(questions, *question): validator
                                           for validator, found in registration.validators.items()
                                           for question in found}
        maps[registration.question_set][publication_id] = validate_publication_id
    return _per_catalog(maps)
