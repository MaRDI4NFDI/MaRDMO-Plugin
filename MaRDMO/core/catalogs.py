'''MaRDMO's catalogs: each declares itself, the shared code looks it up here (#198).

A catalog is a package (``model``, ``algorithm``, ``workflow``, ``search``)
whose module ``catalog.py`` declares its :class:`Registration`: its catalog
entries (:class:`Catalog`) and its question set.  The registry
(:data:`CATALOG_PACKAGES`, :func:`registrations`) loads these declarations
when first needed, as Django loads the apps of ``INSTALLED_APPS``; the shared
code names no catalog.  A catalog of the questionnaire is a MaRDMO catalog
if a registration has an entry for it (:func:`catalog_of`).
``tests/unit/test_catalogs.py`` names what a declaration is missing.

The workers are given by their import path and loaded when first used: the
router and the provider settings import this module early, before the
workers can be imported.
'''
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from importlib import import_module
from typing import Optional

from .constants import BASE_URI

MODEL, ALGORITHM, WORKFLOW, SEARCH = 'model', 'algorithm', 'workflow', 'search'
'''The kinds of catalogs: what is documented (or searched) with it.'''

CATALOG_PACKAGES = ('model', 'algorithm', 'workflow', 'search')
'''The packages of MaRDMO's catalogs; each has a module ``catalog.py`` with its :class:`Registration`.'''


def _imported(path):
    '''The object at the import path *path* (``MaRDMO.model.handlers.Information``).'''
    module, _, name = path.rpartition('.')
    return getattr(import_module(module), name)


@dataclass(frozen=True)
class Catalog:
    '''One of MaRDMO's catalogs.

    Attributes:
        name:       The catalog's slug, the last part of its URI.
        kind:       :data:`MODEL`, :data:`ALGORITHM`, :data:`WORKFLOW` or :data:`SEARCH`.
        questions:  The question set of ``data/questions.json`` it is answered with.
        template:   The template of its preview.
        worker:     Import path of the class that prepares the export
                    (``MaRDMO.model.worker.PrepareModel``); empty for the search.
        check:      Import path of its checks, a subclass of
                    :class:`~MaRDMO.export.checks.ChecksBase` (``MaRDMO.model.checks.ModelChecks``).
        subset:     It has only part of the questions of its question set
                    (model basics, #168): the answers are read for its own.
    '''
    name: str
    kind: str
    questions: Optional[str]
    template: str
    worker: str = ''
    check: str = ''
    subset: bool = False

    @property
    def uri(self):
        '''The catalog's URI.'''
        return f'{BASE_URI}questions/{self.name}'

    @property
    def documents(self):
        '''Whether it documents items for the export (all but the search).'''
        return self.kind != SEARCH

    @cached_property
    def prepare_class(self):
        '''The class of :attr:`worker`, imported when first used.'''
        return _imported(self.worker)

    @cached_property
    def checks_class(self):
        '''The class of :attr:`check`, imported when first used.'''
        return _imported(self.check)


@dataclass(frozen=True)
class Registration:
    '''What a catalog package declares about itself (its ``catalog.py``, ``REGISTRATION``).

    The questions are named by ``(question set, question)`` of the package's
    question set (:attr:`question_set`); classes and functions by their import
    path, loaded when first used.

    Attributes:
        catalogs:    Its catalog entries (:class:`Catalog`).
        questions:   ``{question set: path of its questions.json}``, relative
                     to the MaRDMO package.
        information: Import path of its handler class (the hydration of its items).
        handlers:    The questions with a handler of that class: ``{question: method}``.
        relations:   The relation questions, handled by the general relation
                     handler (:meth:`MaRDMO.components.fill.relations.Information.relation`).
        validators:  The pre-save validators: ``{validator: [question, …]}``.
        targets:     Import path of the function that maps the attribute URI
                     of a relation question to the section of its items
                     (``{'question_set', 'question_id', 'prefix'}``).
        fills:       ``{section prefix: (item type, fill method of the handler class)}``:
                     how a related item of a portal or Wikidata is filled in.
        routing:     The relations a publication of its catalogs can have
                     (:func:`MaRDMO.components.publication.constants.routing`): rules with the
                     ``classes`` of the related items, the relation types
                     (``props``, ``relation``) and the answer (``relatant``).
    '''
    catalogs: tuple
    questions: dict = field(default_factory=dict)
    information: str = ''
    handlers: dict = field(default_factory=dict)
    relations: tuple = ()
    validators: dict = field(default_factory=dict)
    targets: str = ''
    fills: dict = field(default_factory=dict)
    routing: tuple = ()

    @property
    def question_set(self):
        '''The question set its tables refer to (the first of :attr:`questions`), or ``None``.'''
        return next(iter(self.questions), None)

    @cached_property
    def information_class(self):
        '''The class of :attr:`information`, imported when first used.'''
        return _imported(self.information)

    @cached_property
    def relation_targets(self):
        '''The function of :attr:`targets`, imported when first used.'''
        return _imported(self.targets)


@lru_cache(maxsize=None)
def registrations():
    '''The :class:`Registration` of every package of :data:`CATALOG_PACKAGES`, loaded when first needed.'''
    return tuple(import_module(f'MaRDMO.{package}.catalog').REGISTRATION for package in CATALOG_PACKAGES)


def catalogs():
    '''MaRDMO's catalogs by name: the entries of all registrations.'''
    return {catalog.name: catalog for registration in registrations() for catalog in registration.catalogs}


def documenting():
    '''The names of the catalogs that document items (all but the search).'''
    return tuple(name for name, catalog in catalogs().items() if catalog.documents)


def registration_of(catalog):
    '''The :class:`Registration` that declares the :class:`Catalog` *catalog*.'''
    return next(registration for registration in registrations() if catalog in registration.catalogs)


def catalog_of(project_or_catalog):
    '''The :class:`Catalog` of a project, an RDMO catalog or a catalog URI; ``None`` if it is not MaRDMO's.'''
    catalog = getattr(project_or_catalog, 'catalog', project_or_catalog)
    if catalog is None:
        return None
    return catalogs().get(str(catalog).rsplit('/', 1)[-1])
