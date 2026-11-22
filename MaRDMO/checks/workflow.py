'''Workflow Documentation check mixin.'''
from django.utils.translation import gettext as _, gettext_noop as N_

from ..workflow.catalog import CATALOG_WORKFLOW
from ..getters import get_options
from .base import SOFTWARE_REFERENCE_CHECKS, without_page
from ..validators import archive_year_problem, count_problem, doi_problem, size_problem


class WorkflowMixin:
    '''Checks for Interdisciplinary Workflow catalog entries.'''

    # -------------------------------------------------------------------------
    # Workflow Documentation Checks
    # -------------------------------------------------------------------------

    def workflow(self, project, data):
        '''Check Interdisciplinary Workflow documentation completeness.

        Verifies mandatory Research Objective, Process Step link,
        Model/Task cross-dependency, and all five reproducibility fields.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        for ikey, ivalue in data.get('workflow', {}).items():
            page_name = self._page('workflow', ikey, ivalue)

            if not ivalue.get('objective'):
                self._missing(N_('Interdisciplinary Workflow'), page_name, _('Missing Research Objective'), 'objective')

            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationPS',
                from_class = N_('Interdisciplinary Workflow'),
                to_class   = N_('Process Step')
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationWF',
                from_class = N_('Interdisciplinary Workflow')
            )

            for pair in ivalue.get('model_task_pairs', []):
                if pair['has_model'] and not pair['has_tasks']:
                    self._missing(N_('Interdisciplinary Workflow'), page_name, _('Missing Computational Task'), 'model_task_pairs')
                elif pair['has_tasks'] and not pair['has_model']:
                    self._missing(N_('Interdisciplinary Workflow'), page_name, _('Missing Mathematical Model'), 'model_task_pairs')

            repro_fields = [
                ('mathematical',    N_('Mathematical Reproducibility')),
                ('runtime',         N_('Runtime Reproducibility')),
                ('result',          N_('Reproducibility of Results')),
                ('originalplatform', N_('Reproducibility on Original Platform')),
                ('otherplatform',   N_('Reproducibility on Other Platform')),
            ]
            for key, label in repro_fields:
                if not ivalue.get(key):
                    self._missing(N_('Interdisciplinary Workflow'), page_name, _('Missing {item}').format(item=_(label)), key)

    def step(self, project, data):
        '''Check Process Step documentation completeness.

        Verifies mandatory Input/Output Data Sets, Academic Discipline, and
        that at least one complete path (Algorithm+Software+Hardware+SoftwareReq
        or Method+Instrument+MethodProtocol) is documented.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        options = get_options()
        for ikey, ivalue in data.get('processstep', {}).items():
            page_name = self._page('processstep', ikey, ivalue)
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationIDS',
                from_class = N_('Process Step'),
                to_class   = N_('Input Data Set')
            )
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationODS',
                from_class = N_('Process Step'),
                to_class   = N_('Output Data Set')
            )
            if not ivalue.get('RFRelatant'):
                self._missing(N_('Process Step'), page_name, _('Missing Academic Discipline'), 'RFRelatant')
            else:
                self._check_without_section_items(
                    items        = ivalue.get('RFRelatant', {}),
                    parent_page  = page_name,
                    parent_class = N_('Process Step'),
                    item_class   = N_('Academic Discipline'),
                    items_field  = 'RFRelatant'
                )

            if ivalue.get('algorithm_software_pairs'):
                for pair in ivalue['algorithm_software_pairs']:
                    if not pair['has_primary']:
                        self._missing(N_('Process Step'), page_name, _('Missing Algorithm'), 'algorithm_software_pairs')
                    elif without_page(pair['primary']):
                        self.err.append(self._error(
                            N_('Process Step'), page_name,
                            _('Selected Algorithm not found in Algorithm Section'),
                            field='algorithm_software_pairs'
                        ))
                    if not pair['has_qualifier']:
                        self._missing(N_('Process Step'), page_name, _('Missing Software (Algorithm Path)'),
                                      'algorithm_software_pairs')
                    elif without_page([pair['qualifier']]):
                        self.err.append(self._error(
                            N_('Process Step'), page_name,
                            _('Selected Software not found in Software Section'),
                            field='algorithm_software_pairs'
                        ))
                    if not pair.get('hardware'):
                        self._missing(N_('Process Step'), page_name, _('Missing Hardware (Algorithm Path)'),
                                      'algorithm_software_pairs')
                    elif without_page([pair['hardware']]):
                        self.err.append(self._error(
                            N_('Process Step'), page_name,
                            _('Selected Hardware not found in Hardware Section'),
                            field='algorithm_software_pairs'
                        ))
                    if not pair.get('software_doc'):
                        self._missing(N_('Process Step'), page_name, _('Missing Software Requirements'), 'algorithm_software_pairs')
                    else:
                        self._check_doc_entries(
                            pair['software_doc'], options, page_name,
                            N_('Software Requirements'), doc_field='algorithm_software_pairs'
                        )

            if ivalue.get('method_instrument_pairs'):
                self._check_without_section_items(
                    items        = ivalue.get('MRelatant', {}),
                    parent_page  = page_name,
                    parent_class = N_('Process Step'),
                    item_class   = N_('Method'),
                    items_field  = 'MRelatant'
                )
                self._check_without_section_items(
                    items        = ivalue.get('IRelatant', {}),
                    parent_page  = page_name,
                    parent_class = N_('Process Step'),
                    item_class   = N_('Instrument'),
                    items_field  = 'IRelatant'
                )
                for pair in ivalue['method_instrument_pairs']:
                    if not pair['has_primary']:
                        self._missing(N_('Process Step'), page_name, _('Missing Method'), 'method_instrument_pairs')
                    if not pair['has_qualifier']:
                        self._missing(N_('Process Step'), page_name, _('Missing Instrument'), 'method_instrument_pairs')
                    if not pair.get('method_doc'):
                        self._missing(N_('Process Step'), page_name, _('Missing Method Protocol'), 'method_instrument_pairs')
                    else:
                        self._check_doc_entries(
                            pair['method_doc'], options, page_name,
                            N_('Method Protocol'), doc_field='method_instrument_pairs'
                        )

    def workflow_algorithm(self, project, data):
        '''Check Algorithm documentation completeness for the workflow catalog.

        Verifies that each algorithm page has at least one Algorithmic Task
        and one Software link.  For user-defined tasks (``user:`` ID),
        also validates name and description.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        for ikey, ivalue in data.get('algorithm', {}).items():
            page_name = self._page('algorithm', ikey, ivalue)
            if not ivalue.get('PRelatant'):
                self._missing(N_('Algorithm'), page_name, _('Missing Algorithmic Task'), 'PRelatant')
            else:
                self._check_without_section_items(
                    items        = ivalue.get('PRelatant', {}),
                    parent_page  = page_name,
                    parent_class = N_('Algorithm'),
                    item_class   = N_('Algorithmic Task'),
                    items_field  = 'PRelatant'
                )
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = N_('Algorithm'),
                to_class   = N_('Software')
            )

    def workflow_software(self, project, data):
        '''Check Software documentation completeness for the workflow catalog.

        Validates programming language inline items, optional software
        dependencies, and reference entries.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        for ikey, ivalue in data.get('software', {}).items():
            page_name = self._page('software', ikey, ivalue)
            self._check_without_section_items(
                items        = ivalue.get('programminglanguage', {}),
                parent_page  = page_name,
                parent_class = N_('Software'),
                item_class   = N_('Programming Language'),
                items_field  = 'programminglanguage'
            )
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = N_('Software'),
                to_class   = N_('Software')
            )
            if not ivalue.get('reference'):
                self._missing(N_('Software'), page_name, _('Missing Reference'), 'reference')
            else:
                self._check_references(ivalue['reference'], 'Software', page_name, SOFTWARE_REFERENCE_CHECKS)

    def hardware(self, project, data):
        '''Check Hardware documentation completeness.

        Verifies that each hardware page has a valid integer compute-node count,
        at least one CPU, valid name/description for user-defined CPUs, and
        integer occurrence and core counts per CPU entry.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        for ikey, ivalue in data.get('hardware', {}).items():
            page_name = self._page('hardware', ikey, ivalue)

            nodes = ivalue.get('nodes')
            if not nodes:
                self._missing(N_('Hardware'), page_name, _('Missing Number of Compute Nodes'), 'nodes')
            elif problem := count_problem(nodes):
                self._invalid(N_('Hardware'), page_name,
                              _('Invalid Number of Compute Nodes: {problem}').format(problem=problem), 'nodes', [nodes])

            cpu_entries = ivalue.get('cpu_entries', [])
            if not cpu_entries:
                self._missing(N_('Hardware'), page_name, _('Missing CPU'), 'cpu_entries')
            else:
                self._check_without_section_items(
                    items        = ivalue.get('cpu', {}),
                    parent_page  = page_name,
                    parent_class = N_('Hardware'),
                    item_class   = N_('CPU'),
                    items_field  = 'cpu'
                )
                for entry in cpu_entries:
                    # Occurrence and cores are exported on the CPU model only
                    if not entry.get('id') and not entry.get('name'):
                        self._missing(N_('Hardware'), page_name, _('Missing CPU Model'), 'cpu_entries')
                    if not entry.get('count'):
                        self._missing(N_('Hardware'), page_name, _('Missing CPU Occurrence in Hardware'), 'cpu_entries')
                    elif problem := count_problem(entry['count']):
                        self._invalid(N_('Hardware'), page_name,
                                      _('Invalid CPU Occurrence: {problem}').format(problem=problem), 'cpu_entries',
                                      [entry['count']])
                    if not entry.get('cores'):
                        self._missing(N_('Hardware'), page_name, _('Missing Number of Processor Cores'), 'cpu_entries')
                    elif problem := count_problem(entry['cores']):
                        self._invalid(N_('Hardware'), page_name,
                                      _('Invalid Number of Processor Cores: {problem}').format(problem=problem),
                                      'cpu_entries', [entry['cores']])

    def dataset(self, project, data):
        '''Check Data Set documentation completeness.

        Verifies mandatory fields: binary/text type, proprietary flag, file
        format, data size (option + valid number), publication statement, and
        archival statement (with a valid 4-digit year when Yes is selected).

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        options = get_options()
        for ikey, ivalue in data.get('dataset', {}).items():
            page_name = self._page('dataset', ikey, ivalue)

            if not ivalue.get('BinaryText'):
                self._missing(N_('Data Set'), page_name, _('Missing Data Set Type'), 'BinaryText')

            if not ivalue.get('Proprietary'):
                self._missing(N_('Data Set'), page_name, _('Missing Data Set Proprietary'), 'Proprietary')

            if not ivalue.get('FileFormat'):
                self._missing(N_('Data Set'), page_name, _('Missing File Format'), 'FileFormat')

            size = ivalue.get('Size')
            if not size or not size[0]:
                self._missing(N_('Data Set'), page_name, _('Missing Data Size'), 'Size')
            elif not size[1]:
                self._missing(N_('Data Set'), page_name, _('Missing Data Size Value'), 'Size')
            elif problem := size_problem(size[1], integer=size[0] == options['items']):
                self._invalid(N_('Data Set'), page_name, _('Invalid Data Size Value: {problem}').format(problem=problem),
                              'Size', [size[1]])

            if not ivalue.get('ToPublish') or not ivalue['ToPublish'][0]:
                self._missing(N_('Data Set'), page_name, _('Missing Data Set Publication Statement'), 'ToPublish')
            elif (
                ivalue['ToPublish'][0] == options['YesText']
                and len(ivalue['ToPublish']) > 1
                and doi_problem(str(ivalue['ToPublish'][1] or ''))
            ):
                self._invalid(N_('Data Set'), page_name,
                              _('Invalid Publication DOI: {problem}').format(problem=doi_problem(str(ivalue['ToPublish'][1]))),
                              'ToPublish', [ivalue['ToPublish'][1]])

            to_archive = ivalue.get('ToArchive')
            if not to_archive or not to_archive[0]:
                self._missing(N_('Data Set'), page_name, _('Missing Data Set Archival Statement'), 'ToArchive')
            elif to_archive[0] == options['YesText']:
                if not to_archive[1]:
                    self._missing(N_('Data Set'), page_name, _('Missing Archival Year'), 'ToArchive')
                else:
                    problem = archive_year_problem(to_archive[1])
                    if problem:
                        self._invalid(N_('Data Set'), page_name,
                                      _('Invalid Archival Year: {problem}').format(problem=problem), 'ToArchive',
                                      [to_archive[1]])

    # -------------------------------------------------------------------------
    # Run method
    # -------------------------------------------------------------------------

    def run_workflow(self, project, data, catalog=None):
        '''Run all workflow-catalog checks and return the collected error list.

        Executes, in order: ID/Name/Description, single-line text, workflow, process step,
        algorithm, software, hardware, dataset, and publication checks.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.

        Returns:
            Sorted list of :class:`~MaRDMO.problems.Problem`, empty when
            all checks pass.
        '''
        self._tab_names(project, data)
        self.id_name_description(project, data, CATALOG_WORKFLOW)
        self.single_line_text(project, data, CATALOG_WORKFLOW)
        self.workflow(project, data)
        self.step(project, data)
        self.workflow_algorithm(project, data)
        self.workflow_software(project, data)
        self.hardware(project, data)
        self.dataset(project, data)
        self.publication(project, data, CATALOG_WORKFLOW)
        return self._finalise()
