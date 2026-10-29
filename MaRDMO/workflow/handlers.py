'''Module containing Handlers for the Interdisciplinary Workflow Documentation.

Information inherits _entry, _collect_existing_ids, _hydrate_relatants,
and _fill from BaseInformation (MaRDMO/handler_base.py).
'''

import logging
from functools import partial

from ..handler_base import BaseInformation, _RelatantSpec, _fetch_by_source
from ..constants import BASE_URI
from ..getters import (
    get_items, get_mathalgodb, get_mathmoddb, get_options,
    get_properties, get_questions, get_sparql_query, get_url,
)
from ..helpers import value_editor
from ..adders import add_basics, add_relations_flexible, add_relations_static
from ..queries import query_sparql

from .constants import PROPS
from .models import Cpu, ProcessStep, Hardware, DataSet, Workflow

logger = logging.getLogger(__name__)


class Information(BaseInformation):
    '''Handlers for the Workflow Documentation questionnaire.'''

    _ENTITY_KEYS = ('Workflow', 'Algorithm', 'Software', 'Hardware', 'Data Set', 'Process Step',
                    'Publication')

    def __init__(self):
        '''Load workflow questions, base URI, RDMO options, and MathAlgoDB registry.'''
        self.questions  = get_questions('workflow') | get_questions('publication')
        self.base       = BASE_URI
        self.options    = get_options()
        self.mathalgodb = get_mathalgodb()
        self.mathmoddb  = get_mathmoddb()

    # ------------------------------------------------------------------ #
    #  Public entry points (called by router via post_save signal)         #
    # ------------------------------------------------------------------ #

    def workflow(self, instance):
        '''Handle Workflow ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Workflow', self._fill_workflow_batch)

    def software(self, instance):
        '''Handle Software ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Software', self._fill_software_batch)

    def hardware(self, instance):
        '''Handle Hardware ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Hardware', self._fill_hardware_batch)

    def processor_cores(self, instance):
        '''Handle CPU ID save: query and write number of processor cores.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        if not instance.external_id:
            return

        data_by_id = _fetch_by_source(
            [(instance.text, instance.external_id, instance.set_index)],
            'workflow/queries/cpu_mardi.sparql',
            'workflow/queries/cpu_wikidata.sparql',
            Cpu,
        )
        data = data_by_id.get(instance.external_id)
        if not data or not data.cores:
            return

        value_editor(
            project=instance.project,
            uri=f'{self.base}{self.questions["Hardware"]["Cores"]["uri"]}',
            info={'text': data.cores,
                  'set_prefix': instance.set_prefix,
                  'set_index': instance.set_index})

    def data_set(self, instance):
        '''Handle Data Set ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Data Set', self._fill_data_set_batch)

    def algorithm(self, instance):
        '''Handle Algorithm ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Algorithm', self._fill_algorithm_batch)

    def process_step(self, instance):
        '''Handle Process Step ID save: hydrate basics and cascade to all related entities.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Process Step', self._fill_process_step_batch)

    def model(self, instance):
        '''Handle Workflow Model ID save: add linked Tasks from the MaRDI Portal.

        Queries the MaRDI Portal for computational tasks linked to the selected model
        and adds any not yet present as Task values. Already-present tasks are left
        untouched so tasks from previously selected models are preserved.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''

        if not instance.external_id:
            return

        tasks = self._fetch_tasks_for_model(instance.external_id)

        if not tasks:
            return

        for idx, (identifier, label, description) in enumerate(tasks):
            value_editor(
                project = instance.project,
                uri = f'{self.base}{self.questions["Workflow"]["Task"]["uri"]}',
                info = {
                    'external_id': identifier,
                    'text': f'{label} ({description}) [mardi]',
                    'collection_index': idx,
                    'set_prefix': instance.set_prefix,
                    'set_index': instance.set_index
                },
            )

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _fetch_tasks_for_model(self, model_id):
        '''Run ``task_mardi.sparql`` for *id_value* and return parsed task tuples.

        Args:
            id_value: Raw Wikibase QID string (e.g. ``"Q1234"``), without prefix.

        Returns:
            List of ``(identifier, label, description)`` tuples, or empty list when
            the portal returns no results or the query fails.
        '''
        _, id_value = model_id.split(':')

        query = get_sparql_query('workflow/queries/task_mardi.sparql').format(
            id_value,
            **get_items(),
            **get_properties(),
        )

        results = query_sparql(query, get_url('mardi', 'sparql'))

        if not results or not results[0].get('usedBy', {}).get('value'):
            return []

        tasks = []
        for raw in results[0]['usedBy']['value'].split(' <|> '):
            try:
                identifier, label, description = raw.split(' || ')
                tasks.append((identifier, label, description))
            except ValueError:
                logger.warning('Unexpected task format, skipping: %r', raw)

        return tasks

    # ------------------------------------------------------------------ #
    #  Batch _fill_* methods (one SPARQL query for N entities)            #
    # ------------------------------------------------------------------ #

    def _fill_workflow_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Workflow pages with a single SPARQL query per source.

        Writes basics, research objective, procedure (long description),
        mathematical models with task qualifiers, process-step relatant pointers,
        reproducibility statements (Yes + optional comment), and transferability
        comments.  Then cascades into the Process Step section via
        :meth:`_hydrate_relatants`.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix (default ``""``).
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return

        workflow_q = self.questions['Workflow']
        data_by_id = _fetch_by_source(
            items,
            'workflow/queries/workflow_mardi.sparql',
            'workflow/queries/workflow_wikidata.sparql',
            Workflow,
        )
        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Workflow', index=(0, set_index))

            if data.research_objective:
                value_editor(
                    project=project,
                    uri=f'{self.base}{workflow_q["Objective"]["uri"]}',
                    info={'text': ' | '.join(data.research_objective),
                          'set_prefix': set_index})

            for i, proc in enumerate(data.procedure):
                value_editor(
                    project=project,
                    uri=f'{self.base}{workflow_q["Long Description"]["uri"]}',
                    info={'text': proc, 'set_prefix': set_index, 'collection_index': i})

            model_order = []
            model_tasks = {}
            for raw in data.uses_model:
                parts = raw.split(' || ')
                while len(parts) < 6:
                    parts.append('')
                model_id, model_label, model_desc, task_id, task_label, task_desc = parts[:6]
                if not model_id:
                    continue
                if model_id not in model_tasks:
                    model_order.append((model_id, model_label, model_desc))
                    model_tasks[model_id] = []
                if task_id:
                    model_tasks[model_id].append((task_id, task_label, task_desc))

            for model_idx, (model_id, model_label, model_desc) in enumerate(model_order):
                source = model_id.split(':')[0]
                value_editor(
                    project=project,
                    uri=f'{self.base}{workflow_q["Model"]["uri"]}',
                    info={'text': f'{model_label} ({model_desc}) [{source}]',
                          'external_id': model_id,
                          'set_prefix': f"{set_index}|0", 'set_index': model_idx})
                for task_idx, (task_id, task_label, task_desc) in enumerate(model_tasks[model_id]):
                    source = task_id.split(':')[0]
                    value_editor(
                        project=project,
                        uri=f'{self.base}{workflow_q["Task"]["uri"]}',
                        info={'text': f'{task_label} ({task_desc}) [{source}]',
                              'external_id': task_id,
                              'set_prefix': f"{set_index}|0", 'set_index': model_idx,
                              'collection_index': task_idx})

            for i, ps in enumerate(data.contains_process_step):
                if ps.id:
                    source = ps.id.split(':')[0]
                    value_editor(
                        project=project,
                        uri=f'{self.base}{workflow_q["PSRelatant"]["uri"]}',
                        info={'text': f'{ps.label} ({ps.description}) [{source}]',
                              'external_id': ps.id,
                              'set_prefix': set_index, 'collection_index': i})

            for value, comment, q_key in [
                (data.mathematical,     data.mathematical_comment,    'Mathematical'),
                (data.runtime,          data.runtime_comment,         'Runtime'),
                (data.result,           data.result_comment,          'Result'),
                (data.originalplatform, data.originalplatform_comment, 'Original Platform'),
                (data.otherplatform,    data.otherplatform_comment,   'Other Platform'),
            ]:
                if value == 'Yes':
                    value_editor(
                        project=project,
                        uri=f'{self.base}{workflow_q[q_key]["uri"]}',
                        info={'option': self.options['YesLargeText'],
                              'text': comment or '',
                              'set_prefix': f"{set_index}|0"})
                elif value == 'No':
                    value_editor(
                        project=project,
                        uri=f'{self.base}{workflow_q[q_key]["uri"]}',
                        info={'option': self.options['No'],
                              'set_prefix': f"{set_index}|0"})

            if data.transferable == 'Yes':
                for i, comment in enumerate(data.transferable_comment):
                    value_editor(
                        project=project,
                        uri=f'{self.base}{workflow_q["Transferability"]["uri"]}',
                        info={'text': comment,
                              'set_prefix': set_index,
                              'set_index': 0, 'collection_index': i})

            add_relations_flexible(
                project=project, data=data,
                props={'keys': PROPS['IW2IW'], 'mapping': self.mathmoddb},
                index={'set_prefix': set_index},
                statement={
                    'relation': f'{self.base}{workflow_q["IntraClassRelation"]["uri"]}',
                    'relatant': f'{self.base}{workflow_q["IntraClassElement"]["uri"]}',
                })

            self._hydrate_publications(project, data.publications, catalog, visited)

            self._hydrate_relatants(
                project=project, data=data, prop_keys=['contains_process_step'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Process Step"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Process Step"]["uri"]}',
                    prefix='PS',
                    fill_method=partial(self._fill, item_type='Process Step',
                                        batch_fill_method=self._fill_process_step_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_process_step_batch,
                ))

    def _fill_hardware_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Hardware pages with a single SPARQL query per source.

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

        hardware   = self.questions['Hardware']
        data_by_id = _fetch_by_source(
            items,
            'workflow/queries/hardware_mardi.sparql',
            'workflow/queries/hardware_wikidata.sparql',
            Hardware,
        )

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Hardware', index=(0, set_index))

            if data.nodes:
                value_editor(
                    project=project,
                    uri=f'{self.base}{hardware["Nodes"]["uri"]}',
                    info={'text': data.nodes, 'set_prefix': set_index})

            for i, cpu in enumerate(data.cpu):
                source, _ = cpu.id.split(':')
                cpu_value, _ = value_editor(
                    project=project,
                    uri=f'{self.base}{hardware["CPU"]["uri"]}',
                    info={'text': f'{cpu.label} ({cpu.description}) [{source}]',
                          'external_id': cpu.id,
                          'set_prefix': f"{set_index}|0", 'set_index': i})
                if cpu.count:
                    value_editor(
                        project=project,
                        uri=f'{self.base}{hardware["Number of CPU"]["uri"]}',
                        info={'text': cpu.count,
                              'set_prefix': f"{set_index}|0", 'set_index': i})
                self.processor_cores(cpu_value)

            self._hydrate_publications(project, data.publications, catalog, visited)

    def _fill_data_set_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Data Set pages with a single SPARQL query per source.

        Writes basics, size, file format, binary/text type, proprietary flag,
        and publication/archival statements.

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

        data_set_q = self.questions['Data Set']
        data_by_id = _fetch_by_source(
            items,
            'workflow/queries/data_set_mardi.sparql',
            'workflow/queries/data_set_wikidata.sparql',
            DataSet,
        )

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Data Set', index=(0, set_index))

            if data.size:
                value_editor(
                    project=project,
                    uri=f'{self.base}{data_set_q["Size"]["uri"]}',
                    info={'text': data.size[1], 'option': data.size[0],
                          'set_prefix': set_index})

            if data.file_format:
                value_editor(
                    project=project,
                    uri=f'{self.base}{data_set_q["File Format"]["uri"]}',
                    info={'text': data.file_format, 'set_prefix': set_index})

            if data.binary_or_text:
                value_editor(
                    project=project,
                    uri=f'{self.base}{data_set_q["Binary or Text"]["uri"]}',
                    info={'option': data.binary_or_text, 'set_prefix': set_index})

            if data.proprietary:
                value_editor(
                    project=project,
                    uri=f'{self.base}{data_set_q["Proprietary"]["uri"]}',
                    info={'option': data.proprietary, 'set_prefix': set_index})

            if data.to_publish:
                value_editor(
                    project=project,
                    uri=f'{self.base}{data_set_q["To Publish"]["uri"]}',
                    info={'text': data.to_publish[1], 'option': data.to_publish[0],
                          'set_prefix': set_index})

            if data.to_archive:
                value_editor(
                    project=project,
                    uri=f'{self.base}{data_set_q["To Archive"]["uri"]}',
                    info={'text': data.to_archive[1][:4], 'option': data.to_archive[0],
                          'set_prefix': set_index})

            self._hydrate_publications(project, data.publications, catalog, visited)

    def _fill_process_step_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Process Step pages with a single SPARQL query per source.

        Writes basics and all relation fields (input/output data sets, algorithms
        with software/hardware qualifiers, experimental methods, fields of work).
        Cascades into Data Set, Algorithm, Software, and Hardware sections via
        :meth:`_hydrate_relatants` instead of relying on signal-driven cascades.

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

        process_step = self.questions['Process Step']
        data_by_id   = _fetch_by_source(
            items,
            'workflow/queries/process_step_mardi.sparql',
            'workflow/queries/process_step_wikidata.sparql',
            ProcessStep,
        )
        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Process Step', index=(0, set_index))

            add_relations_static(
                project=project, data=data,
                props={'keys': PROPS['PS2IDS']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{process_step["Input"]["uri"]}'})

            self._hydrate_relatants(
                project=project, data=data, prop_keys=PROPS['PS2IDS'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Data Set"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Data Set"]["uri"]}',
                    prefix='DS',
                    fill_method=partial(self._fill, item_type='Data Set',
                                        batch_fill_method=self._fill_data_set_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_data_set_batch,
                ))

            add_relations_static(
                project=project, data=data,
                props={'keys': PROPS['PS2ODS']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{process_step["Output"]["uri"]}'})

            self._hydrate_relatants(
                project=project, data=data, prop_keys=PROPS['PS2ODS'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Data Set"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Data Set"]["uri"]}',
                    prefix='DS',
                    fill_method=partial(self._fill, item_type='Data Set',
                                        batch_fill_method=self._fill_data_set_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_data_set_batch,
                ))

            add_relations_static(
                project=project, data=data,
                props={'keys': PROPS['PS2A']},
                index={'set_prefix': f'{set_index}|0'},
                statement={
                    'relatant':      f'{self.base}{process_step["Algorithm"]["uri"]}',
                    'platform':      f'{self.base}{process_step["Software"]["uri"]}',
                    'hardware':      f'{self.base}{process_step["Hardware"]["uri"]}',
                    'documentation': (
                        f'{self.base}{process_step["Software-Documentation"]["uri"]}'
                    ),
                    'parameter':     f'{self.base}{process_step["Algorithm-Parameter"]["uri"]}',
                })

            self._hydrate_relatants(
                project=project, data=data, prop_keys=PROPS['PS2A'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Algorithm"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Algorithm"]["uri"]}',
                    prefix='A',
                    fill_method=partial(self._fill, item_type='Algorithm',
                                        batch_fill_method=self._fill_algorithm_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_algorithm_batch,
                ))

            self._hydrate_qualifier_entities(
                project=project, data=data, prop_keys=PROPS['PS2A'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Software"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Software"]["uri"]}',
                    prefix='S',
                    fill_method=partial(self._fill, item_type='Software',
                                        batch_fill_method=self._fill_software_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_software_batch,
                ))

            self._hydrate_qualifier_entities(
                project=project, data=data,
                prop_keys=PROPS['PS2A'] + PROPS['PS2M'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Hardware"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Hardware"]["uri"]}',
                    prefix='HW',
                    fill_method=partial(self._fill, item_type='Hardware',
                                        batch_fill_method=self._fill_hardware_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_hardware_batch,
                ),
                attr='hardware')

            add_relations_static(
                project=project, data=data,
                props={'keys': PROPS['PS2M']},
                index={'set_prefix': f'{set_index}|0'},
                statement={
                    'relatant':      f'{self.base}{process_step["Method"]["uri"]}',
                    'platform':      f'{self.base}{process_step["Instrument"]["uri"]}',
                    'hardware':      f'{self.base}{process_step["Hardware"]["uri"]}',
                    'documentation': (
                        f'{self.base}{process_step["Method-Documentation"]["uri"]}'
                    ),
                    'parameter':     f'{self.base}{process_step["Method-Parameter"]["uri"]}',
                })

            add_relations_static(
                project=project, data=data,
                props={'keys': PROPS['PS2F']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{process_step["RFRelatant"]["uri"]}'})

            self._hydrate_publications(project, data.publications, catalog, visited)
