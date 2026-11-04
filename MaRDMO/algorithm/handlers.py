'''Module containing Handlers for the Algorithm Documentation.

Information inherits _entry, _collect_existing_ids, _hydrate_relatants,
and _fill from BaseInformation (MaRDMO/handler_base.py).

All batch methods accept catalog='' (unused but required by the shared
_fill and _hydrate_relatants signatures).
'''

import logging
from functools import partial

from .constants import PROPS
from .models import Benchmark, Problem

from ..handler_base import BaseInformation, _RelatantSpec, _fetch_by_source
from ..constants import BASE_URI
from ..getters import (
    get_mathalgodb,
    get_questions,
)
from ..adders import (
    add_basics,
    add_references,
    add_relations_flexible,
    add_relations_static,
)

logger = logging.getLogger(__name__)


class Information(BaseInformation):
    '''Handlers for the Algorithm Documentation questionnaire.'''

    _ENTITY_KEYS = ('Algorithm', 'Problem', 'Software', 'Benchmark', 'Publication')

    def __init__(self):
        '''Load algorithm and publication questions, MathAlgoDB registry, and base URI.'''
        self.questions  = get_questions('algorithm') | get_questions('publication')
        self.mathalgodb = get_mathalgodb()
        self.base       = BASE_URI

    # ------------------------------------------------------------------ #
    #  Public entry points (called by router via post_save signal)         #
    # ------------------------------------------------------------------ #

    def benchmark(self, instance):
        '''Handle Benchmark ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Benchmark', self._fill_benchmark_batch)

    def software(self, instance):
        '''Handle Software ID save: hydrate basics and cascade to Benchmark.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Software', self._fill_software_batch)

    def problem(self, instance):
        '''Handle Algorithmic Problem ID save: hydrate basics and cascade to Benchmark.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Problem', self._fill_problem_batch)

    def algorithm(self, instance):
        '''Handle Algorithm ID save: hydrate basics and cascade to Problem and Software.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Algorithm', self._fill_algorithm_batch)

    # ------------------------------------------------------------------ #
    #  Batch _fill_* methods (one SPARQL query for N entities)            #
    # ------------------------------------------------------------------ #

    def _fill_benchmark_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Benchmark pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix (default ``""``).
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return
        if visited is None:
            visited = set()

        benchmark  = self.questions['Benchmark']
        data_by_id = _fetch_by_source(
            items,
            'algorithm/queries/benchmark_mardi.sparql',
            'algorithm/queries/benchmark_wikidata.sparql',
            Benchmark,
        )
        if not data_by_id:
            return

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Benchmark', index=(0, set_index))

            add_references(project=project, data=data,
                           uri=f'{self.base}{benchmark["Reference"]["uri"]}',
                           set_prefix=set_index)

            self._hydrate_publications(project, data.publications,
                                       catalog, visited)

    def _fill_problem_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Algorithmic Problem pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix (default ``""``).
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return
        if visited is None:
            visited = set()

        problem    = self.questions['Problem']
        data_by_id = _fetch_by_source(
            items,
            'algorithm/queries/problem_mardi.sparql',
            'algorithm/queries/problem_wikidata.sparql',
            Problem,
        )
        if not data_by_id:
            return

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Problem', index=(0, set_index))

            add_relations_static(
                project=project, data=data,
                props={'keys': PROPS['P2B']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{problem["BRelatant"]["uri"]}'})

            self._hydrate_relatants(
                project=project, data=data, prop_keys=PROPS['P2B'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Benchmark"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Benchmark"]["uri"]}',
                    prefix='B',
                    fill_method=partial(self._fill, item_type='Benchmark',
                                        batch_fill_method=self._fill_benchmark_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_benchmark_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': PROPS['Problem'], 'mapping': self.mathalgodb},
                index={'set_prefix': set_index},
                statement={
                    'relation': f'{self.base}{problem["IntraClassRelation"]["uri"]}',
                    'relatant': f'{self.base}{problem["IntraClassElement"]["uri"]}',
                })
