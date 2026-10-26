'''Algorithm Documentation check mixin.'''

from rdmo.domain.models import Attribute

from ..constants import BASE_URI, CATALOG_ALGORITHM
from .base import BENCHMARK_REFERENCE_CHECKS, SOFTWARE_REFERENCE_CHECKS


class AlgorithmMixin:
    '''Checks for Algorithm catalog entries.'''

    # -------------------------------------------------------------------------
    # Algorithm Documentation Checks
    # -------------------------------------------------------------------------

    def algorithm(self, project, data):
        '''Check Algorithm documentation completeness.

        Verifies that each algorithm page has mandatory Algorithmic Task and
        Software links, and valid Algorithm–to–Algorithm relations.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        values = project.values.filter(
            snapshot=None,
            attribute=Attribute.objects.get(uri=f'{BASE_URI}domain/algorithm')
        )
        for ikey, ivalue in data.get('algorithm', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationP',
                from_class = 'Algorithm',
                to_class   = 'Algorithmic Task'
            )
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = 'Algorithm',
                to_class   = 'Software'
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationA',
                from_class = 'Algorithm')

    def algo_problem(self, project, data):
        '''Check Algorithmic Task documentation completeness.

        Verifies valid Algorithmic Task–to–Task relations and, if a Benchmark
        is selected, that it exists in the Benchmark section.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/problem')
        )
        for ikey, ivalue in data.get('problem', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationB',
                from_class = 'Algorithmic Task',
                to_class   = 'Benchmark'
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationP',
                from_class = 'Algorithmic Task'
            )

    def software(self, project, data):
        '''Check Software documentation completeness.

        Verifies that any selected Benchmark or Software dependency exists in
        its section, and that reference entries have a corresponding value when
        their option is selected.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/software')
        )
        for ikey, ivalue in data.get('software', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationB',
                from_class = 'Software',
                to_class   = 'Benchmark'
            )
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = 'Software',
                to_class   = 'Software'
            )
            self._check_without_section_items(
                items        = ivalue.get('programminglanguage', {}),
                parent_page  = page_name,
                parent_class = 'Software',
                item_class   = 'Programming Language'
            )
            if not ivalue.get('reference'):
                self.err.append(self._error('Software', page_name, 'Missing Reference'))
            else:
                self._check_references(ivalue['reference'], 'Software', page_name, SOFTWARE_REFERENCE_CHECKS)

    def benchmark(self, project, data):
        '''Check Benchmark documentation completeness.

        Verifies that any reference entries (DOI, MORwiki ID, URL fields) have
        a corresponding value when their option is selected.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/benchmark')
        )
        for ikey, ivalue in data.get('benchmark', {}).items():
            page_name = values.get(set_index=ikey).text
            if not ivalue.get('reference'):
                self.err.append(self._error('Benchmark', page_name, 'Missing Reference'))
            else:
                self._check_references(ivalue['reference'], 'Benchmark', page_name, BENCHMARK_REFERENCE_CHECKS)

    # -------------------------------------------------------------------------
    # Run method
    # -------------------------------------------------------------------------

    def run_algorithm(self, project, data, catalog=None):
        '''Run all algorithm-catalog checks and return the collected error list.

        Executes, in order: ID/Name/Description, algorithm, algorithmic task,
        software, benchmark, and publication checks.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.

        Returns:
            List of human-readable error strings, or an empty list when all
            checks pass.
        '''
        catalog = CATALOG_ALGORITHM
        self.id_name_description(project, data, catalog)
        self.algorithm(project, data)
        self.algo_problem(project, data)
        self.software(project, data)
        self.benchmark(project, data)
        self.publication(project, data, catalog)
        return self._finalise()
