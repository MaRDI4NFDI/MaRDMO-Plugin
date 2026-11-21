'''MaRDMO's catalogs: one entry each, with what the code needs to know about it (#138).

A catalog of the questionnaire is a MaRDMO catalog if it has an entry here;
everything else (the preview, the export, the handlers of the interview, the
checks) looks the catalog up here instead of comparing its URI.  A new
catalog needs one entry, and the tables keyed by catalog
(:mod:`MaRDMO.builders`, :data:`MaRDMO.publication.constants.ROUTING`)
need its rows; ``tests/unit/test_catalogs.py`` names what is missing.

The workers are given by their import path and loaded when first used: the
router and the provider settings import this module early, before the
workers can be imported.
'''
from dataclasses import dataclass
from functools import cached_property
from importlib import import_module
from typing import Optional

from .constants import (
    BASE_URI,
    CATALOG_ALGORITHM_NAME,
    CATALOG_MODEL_BASICS_NAME,
    CATALOG_MODEL_NAME,
    CATALOG_WORKFLOW_NAME,
)

MODEL, ALGORITHM, WORKFLOW, SEARCH = 'model', 'algorithm', 'workflow', 'search'
'''The kinds of catalogs: what is documented (or searched) with it.'''

CATALOG_SEARCH_NAME = 'mardmo-search-catalog'


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


CATALOGS = {catalog.name: catalog for catalog in (
    Catalog(CATALOG_MODEL_NAME, MODEL, 'model', 'MaRDMO/preview_model.html',
            'MaRDMO.model.worker.PrepareModel', 'run_model'),
    Catalog(CATALOG_MODEL_BASICS_NAME, MODEL, 'model', 'MaRDMO/preview_model_basics.html',
            'MaRDMO.model.worker.PrepareModel', 'run_model', subset=True),
    Catalog(CATALOG_ALGORITHM_NAME, ALGORITHM, 'algorithm', 'MaRDMO/preview_algorithm.html',
            'MaRDMO.algorithm.worker.PrepareAlgorithm', 'run_algorithm'),
    Catalog(CATALOG_WORKFLOW_NAME, WORKFLOW, 'workflow', 'MaRDMO/preview_workflow.html',
            'MaRDMO.workflow.worker.PrepareWorkflow', 'run_workflow'),
    Catalog(CATALOG_SEARCH_NAME, SEARCH, None, 'MaRDMO/preview_search.html'),
)}
'''MaRDMO's catalogs by name.'''

DOCUMENTING = tuple(name for name, catalog in CATALOGS.items() if catalog.documents)
'''The names of the catalogs that document items (all but the search).'''


def catalog_of(project_or_catalog):
    '''The :class:`Catalog` of a project, an RDMO catalog or a catalog URI; ``None`` if it is not MaRDMO's.'''
    catalog = getattr(project_or_catalog, 'catalog', project_or_catalog)
    if catalog is None:
        return None
    return CATALOGS.get(str(catalog).rsplit('/', 1)[-1])
