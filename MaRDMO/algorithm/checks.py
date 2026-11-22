'''The checks of the algorithm catalog, on the shared :class:`~MaRDMO.checks.base.ChecksBase`.'''
from django.utils.translation import gettext as _, gettext_noop as N_

from .constants import SECTION_MAP
from .catalog import CATALOG_ALGORITHM
from ..checks.base import ChecksBase, BENCHMARK_REFERENCE_CHECKS, SOFTWARE_REFERENCE_CHECKS


class AlgorithmChecks(ChecksBase):
    '''Checks for Algorithm catalog entries.'''

    section_map = SECTION_MAP
    page_sections = ('algorithm', 'problem', 'software', 'benchmark', 'publication')

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
        for ikey, ivalue in data.get('algorithm', {}).items():
            page_name = self._page('algorithm', ikey, ivalue)
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationP',
                from_class = N_('Algorithm'),
                to_class   = N_('Algorithmic Task')
            )
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = N_('Algorithm'),
                to_class   = N_('Software')
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationA',
                from_class = N_('Algorithm'))

    def algo_problem(self, project, data):
        '''Check Algorithmic Task documentation completeness.

        Verifies valid Algorithmic Task–to–Task relations and, if a Benchmark
        is selected, that it exists in the Benchmark section.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        for ikey, ivalue in data.get('problem', {}).items():
            page_name = self._page('problem', ikey, ivalue)
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationB',
                from_class = N_('Algorithmic Task'),
                to_class   = N_('Benchmark')
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationP',
                from_class = N_('Algorithmic Task')
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
        for ikey, ivalue in data.get('software', {}).items():
            page_name = self._page('software', ikey, ivalue)
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationB',
                from_class = N_('Software'),
                to_class   = N_('Benchmark')
            )
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = N_('Software'),
                to_class   = N_('Software')
            )
            self._check_without_section_items(
                items        = ivalue.get('programminglanguage', {}),
                parent_page  = page_name,
                parent_class = N_('Software'),
                item_class   = N_('Programming Language'),
                items_field  = 'programminglanguage'
            )
            if not ivalue.get('reference'):
                self._missing(N_('Software'), page_name, _('Missing Reference'), 'reference')
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
        for ikey, ivalue in data.get('benchmark', {}).items():
            page_name = self._page('benchmark', ikey, ivalue)
            if not ivalue.get('reference'):
                self._missing(N_('Benchmark'), page_name, _('Missing Reference'), 'reference')
            else:
                self._check_references(ivalue['reference'], 'Benchmark', page_name, BENCHMARK_REFERENCE_CHECKS)

    # -------------------------------------------------------------------------
    # Run method
    # -------------------------------------------------------------------------

    def run(self, project, data, catalog=None):
        '''Run all algorithm-catalog checks and return the collected error list.

        Executes, in order: ID/Name/Description, algorithm, algorithmic task,
        software, benchmark, and publication checks.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.

        Returns:
            Sorted list of :class:`~MaRDMO.problems.Problem`, empty when
            all checks pass.
        '''
        self._tab_names(project, data)
        catalog = CATALOG_ALGORITHM
        self.id_name_description(project, data, catalog)
        self.algorithm(project, data)
        self.algo_problem(project, data)
        self.software(project, data)
        self.benchmark(project, data)
        self.publication(project, data, catalog)
        return self._finalise()

    def _publication_relations(self, ivalue, page_name):
        '''Check the relations of the publication *ivalue* (page *page_name*) the algorithm catalog requires.'''
        # Algorithm mode: optional links, but at least one required
        if ivalue.get('RelationA') or ivalue.get('RelationBS'):
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationA',
                from_class = N_('Publication'),
                to_class   = N_('Algorithm'),
                optional   = True
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationBS',
                from_class = N_('Publication'),
                to_class   = N_('Benchmark/Software'),
                optional   = True
            )
        else:
            self._missing(N_('Publication'), page_name, _('Missing Algorithm, Benchmark, or Software'),
                          'RelationA')
