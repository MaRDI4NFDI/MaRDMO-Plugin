'''Workflow Documentation check mixin.'''

from rdmo.domain.models import Attribute

from ..constants import BASE_URI, CATALOG_WORKFLOW
from ..getters import get_options
from .base import SOFTWARE_REFERENCE_CHECKS
from ..validators import doi_problem


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
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/workflow')
        )
        for ikey, ivalue in data.get('workflow', {}).items():
            page_name = values.get(set_index=ikey).text

            if not ivalue.get('objective'):
                self.err.append(self._error(
                    'Interdisciplinary Workflow', page_name,
                    'Missing Research Objective'
                ))

            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationPS',
                from_class = 'Interdisciplinary Workflow',
                to_class   = 'Process Step'
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationWF',
                from_class = 'Interdisciplinary Workflow'
            )

            for pair in ivalue.get('model_task_pairs', []):
                if pair['has_model'] and not pair['has_tasks']:
                    self.err.append(self._error(
                        'Interdisciplinary Workflow', page_name,
                        'Missing Computational Task'
                    ))
                elif pair['has_tasks'] and not pair['has_model']:
                    self.err.append(self._error(
                        'Interdisciplinary Workflow', page_name,
                        'Missing Mathematical Model'
                    ))

            repro_fields = [
                ('mathematical',    'Mathematical Reproducibility'),
                ('runtime',         'Runtime Reproducibility'),
                ('result',          'Reproducibility of Results'),
                ('originalplatform', 'Reproducibility on Original Platform'),
                ('otherplatform',   'Reproducibility on Other Platform'),
            ]
            for key, label in repro_fields:
                if not ivalue.get(key):
                    self.err.append(self._error(
                        'Interdisciplinary Workflow', page_name,
                        f'Missing {label}'
                    ))

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
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/processstep')
        )
        for ikey, ivalue in data.get('processstep', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationIDS',
                from_class = 'Process Step',
                to_class   = 'Input Data Set'
            )
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationODS',
                from_class = 'Process Step',
                to_class   = 'Output Data Set'
            )
            if not ivalue.get('RFRelatant'):
                self.err.append(self._error(
                    'Process Step', page_name, 'Missing Academic Discipline'
                ))
            else:
                self._check_without_section_items(
                    items        = ivalue.get('RFRelatant', {}),
                    parent_page  = page_name,
                    parent_class = 'Process Step',
                    item_class   = 'Academic Discipline'
                )

            if ivalue.get('algorithm_software_pairs'):
                for pair in ivalue['algorithm_software_pairs']:
                    if not pair['has_primary']:
                        self.err.append(self._error(
                            'Process Step', page_name, 'Missing Algorithm'
                        ))
                    elif 'not found' in pair['primary']:
                        self.err.append(self._error(
                            'Process Step', page_name,
                            'Selected Algorithm not found in Algorithm Section'
                        ))
                    if not pair['has_qualifier']:
                        self.err.append(self._error(
                            'Process Step', page_name,
                            'Missing Software (Algorithm Path)'
                        ))
                    elif pair['qualifier'] == 'not found':
                        self.err.append(self._error(
                            'Process Step', page_name,
                            'Selected Software not found in Software Section'
                        ))
                    if not pair.get('hardware'):
                        self.err.append(self._error(
                            'Process Step', page_name,
                            'Missing Hardware (Algorithm Path)'
                        ))
                    elif pair['hardware'] == 'not found':
                        self.err.append(self._error(
                            'Process Step', page_name,
                            'Selected Hardware not found in Hardware Section'
                        ))
                    if not pair.get('software_doc'):
                        self.err.append(self._error(
                            'Process Step', page_name,
                            'Missing Software Requirements'
                        ))
                    else:
                        self._check_doc_entries(
                            pair['software_doc'], options, page_name,
                            'Software Requirements'
                        )

            if ivalue.get('method_instrument_pairs'):
                self._check_without_section_items(
                    items        = ivalue.get('MRelatant', {}),
                    parent_page  = page_name,
                    parent_class = 'Process Step',
                    item_class   = 'Method'
                )
                self._check_without_section_items(
                    items        = ivalue.get('IRelatant', {}),
                    parent_page  = page_name,
                    parent_class = 'Process Step',
                    item_class   = 'Instrument'
                )
                for pair in ivalue['method_instrument_pairs']:
                    if not pair['has_primary']:
                        self.err.append(self._error(
                            'Process Step', page_name, 'Missing Method'
                        ))
                    if not pair['has_qualifier']:
                        self.err.append(self._error(
                            'Process Step', page_name, 'Missing Instrument'
                        ))
                    if not pair.get('method_doc'):
                        self.err.append(self._error(
                            'Process Step', page_name, 'Missing Method Protocol'
                        ))
                    else:
                        self._check_doc_entries(
                            pair['method_doc'], options, page_name,
                            'Method Protocol'
                        )

    def workflow_algorithm(self, project, data):
        '''Check Algorithm documentation completeness for the workflow catalog.

        Verifies that each algorithm page has at least one Algorithmic Task
        and one Software link.  For user-defined tasks (ID == "not found"),
        also validates name and description.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/algorithm')
        )
        for ikey, ivalue in data.get('algorithm', {}).items():
            page_name = values.get(set_index=ikey).text
            if not ivalue.get('PRelatant'):
                self.err.append(self._error(
                    'Algorithm', page_name, 'Missing Algorithmic Task'
                ))
            else:
                self._check_without_section_items(
                    items        = ivalue.get('PRelatant', {}),
                    parent_page  = page_name,
                    parent_class = 'Algorithm',
                    item_class   = 'Algorithmic Task'
                )
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = 'Algorithm',
                to_class   = 'Software'
            )

    def workflow_software(self, project, data):
        '''Check Software documentation completeness for the workflow catalog.

        Validates programming language inline items, optional software
        dependencies, and reference entries.

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
            self._check_without_section_items(
                items        = ivalue.get('programminglanguage', {}),
                parent_page  = page_name,
                parent_class = 'Software',
                item_class   = 'Programming Language'
            )
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationS',
                from_class = 'Software',
                to_class   = 'Software'
            )
            if not ivalue.get('reference'):
                self.err.append(self._error('Software', page_name, 'Missing Reference'))
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
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/hardware')
        )
        for ikey, ivalue in data.get('hardware', {}).items():
            page_name = values.get(set_index=ikey).text

            nodes = ivalue.get('nodes')
            if not nodes:
                self.err.append(self._error(
                    'Hardware', page_name, 'Missing Number of Compute Nodes'
                ))
            elif not str(nodes).strip().isdigit():
                self.err.append(self._error(
                    'Hardware', page_name,
                    'Invalid Number of Compute Nodes (must be an integer)'
                ))

            cpu_entries = ivalue.get('cpu_entries', [])
            if not cpu_entries:
                self.err.append(self._error('Hardware', page_name, 'Missing CPU'))
            else:
                self._check_without_section_items(
                    items        = ivalue.get('cpu', {}),
                    parent_page  = page_name,
                    parent_class = 'Hardware',
                    item_class   = 'CPU'
                )
                for entry in cpu_entries:
                    if not entry.get('count'):
                        self.err.append(self._error(
                            'Hardware', page_name,
                            'Missing CPU Occurrence in Hardware'
                        ))
                    elif not entry.get('count_valid'):
                        self.err.append(self._error(
                            'Hardware', page_name,
                            'Invalid CPU Occurrence (must be an integer)'
                        ))
                    if not entry.get('cores'):
                        self.err.append(self._error(
                            'Hardware', page_name,
                            'Missing Number of Processor Cores'
                        ))
                    elif not entry.get('cores_valid'):
                        self.err.append(self._error(
                            'Hardware', page_name,
                            'Invalid Number of Processor Cores (must be an integer)'
                        ))

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
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/dataset')
        )
        for ikey, ivalue in data.get('dataset', {}).items():
            page_name = values.get(set_index=ikey).text

            if not ivalue.get('BinaryText'):
                self.err.append(self._error('Data Set', page_name, 'Missing Data Set Type'))

            if not ivalue.get('Proprietary'):
                self.err.append(self._error(
                    'Data Set', page_name, 'Missing Data Set Proprietary'
                ))

            if not ivalue.get('FileFormat'):
                self.err.append(self._error('Data Set', page_name, 'Missing File Format'))

            size = ivalue.get('Size')
            if not size or not size[0]:
                self.err.append(self._error('Data Set', page_name, 'Missing Data Size'))
            elif not size[1]:
                self.err.append(self._error('Data Set', page_name, 'Missing Data Size Value'))
            else:
                val = str(size[1]).strip()
                if size[0] == options['items']:
                    if not val.isdigit():
                        self.err.append(self._error(
                            'Data Set', page_name,
                            'Invalid Data Size Value (must be an integer for items)'
                        ))
                else:
                    try:
                        float(val)
                    except (ValueError, TypeError):
                        self.err.append(self._error(
                            'Data Set', page_name,
                            'Invalid Data Size Value (must be a number)'
                        ))

            if not ivalue.get('ToPublish') or not ivalue['ToPublish'][0]:
                self.err.append(self._error(
                    'Data Set', page_name, 'Missing Data Set Publication Statement'
                ))
            elif (
                ivalue['ToPublish'][0] == options['YesText']
                and len(ivalue['ToPublish']) > 1
                and doi_problem(str(ivalue['ToPublish'][1] or ''))
            ):
                self.err.append(self._error(
                    'Data Set', page_name,
                    f"Invalid Publication DOI: {doi_problem(str(ivalue['ToPublish'][1]))}"
                ))

            to_archive = ivalue.get('ToArchive')
            if not to_archive or not to_archive[0]:
                self.err.append(self._error(
                    'Data Set', page_name, 'Missing Data Set Archival Statement'
                ))
            elif to_archive[0] == options['YesText']:
                if not to_archive[1]:
                    self.err.append(self._error('Data Set', page_name, 'Missing Archival Year'))
                else:
                    val = str(to_archive[1]).strip()
                    if not (len(val) == 4 and val.isdigit()):
                        self.err.append(self._error(
                            'Data Set', page_name,
                            'Invalid Archival Year (must be a 4-digit year)'
                        ))

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
            List of human-readable error strings, or an empty list when all
            checks pass.
        '''
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
