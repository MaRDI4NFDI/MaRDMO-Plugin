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
        check:      The method of :class:`~MaRDMO.checks.Checks` that checks it.
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
        module, _, name = self.worker.rpartition('.')
        return getattr(import_module(module), name)


@dataclass(frozen=True)
class Registration:
    '''What a catalog package declares about itself (its ``catalog.py``, ``REGISTRATION``).

    Attributes:
        catalogs:  Its catalog entries (:class:`Catalog`).
        questions: ``{question set: path of its questions.json}``, relative
                   to the MaRDMO package.
    '''
    catalogs: tuple
    questions: dict = field(default_factory=dict)


@lru_cache(maxsize=None)
def registrations():
    '''The :class:`Registration` of every package of :data:`CATALOG_PACKAGES`, loaded when first needed.'''
    return tuple(import_module(f'{__package__}.{package}.catalog').REGISTRATION for package in CATALOG_PACKAGES)


def catalogs():
    '''MaRDMO's catalogs by name: the entries of all registrations.'''
    return {catalog.name: catalog for registration in registrations() for catalog in registration.catalogs}


def documenting():
    '''The names of the catalogs that document items (all but the search).'''
    return tuple(name for name, catalog in catalogs().items() if catalog.documents)


def catalog_of(project_or_catalog):
    '''The :class:`Catalog` of a project, an RDMO catalog or a catalog URI; ``None`` if it is not MaRDMO's.'''
    catalog = getattr(project_or_catalog, 'catalog', project_or_catalog)
    if catalog is None:
        return None
    return catalogs().get(str(catalog).rsplit('/', 1)[-1])
