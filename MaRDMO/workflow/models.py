'''Dataclasses that represent entities in the Interdisciplinary Workflow
documentation catalog.

Each class maps to one entity type collected from MaRDI Portal and Wikidata during
workflow documentation. Instances are populated from SPARQL query results and
carry the fields needed to render questionnaire answers and export entries.

Provides:

- :class:`ProcessStepUsage` — algorithm/method usage within a process step
- :class:`ProcessStep` — process steps associated with a workflow
- :class:`Software`    — software associated with a workflow
- :class:`Hardware`    — hardware associated with a workflow
- :class:`DataSet`     — data sets associated with a workflow
'''

from dataclasses import dataclass, field
from typing import Optional

from .utils import get_option_text_pair, get_size

from ..getters import get_options
from ..helpers import split_value
from ..models import QueryBatch, Relatant


@dataclass
class ProcessStepUsage:
    '''Usage of an algorithm or method in a process step.

    Covers both algorithm-in-process-step (qualifier=software, hardware=hardware)
    and method-in-process-step (qualifier=instrument, hardware always empty).
    Parsed from a fixed-position 11-field ``||``-delimited main block followed
    by an optional ``>|<``-separated parameters section.
    '''
    id: Optional[str]
    label: Optional[str]
    description: Optional[str]
    qualifier: Optional[str]
    qualifier_label: Optional[str]
    qualifier_description: Optional[str]
    hardware: Optional[str]
    hardware_label: Optional[str]
    hardware_description: Optional[str]
    parameters: Optional[str]
    doi: list
    url: list

    @classmethod
    def from_query(cls, raw: str) -> 'ProcessStepUsage':
        '''Parse ``id||label||desc||q||ql||qd||hw||hwl||hwd||doi||url >|< params``.'''
        options = get_options()
        if ' >|< ' in raw:
            main, parameters = raw.split(' >|< ', 1)
        else:
            main, parameters = raw, None
        parts = main.split(' || ')
        while len(parts) < 11:
            parts.append('')
        return cls(
            id=parts[0] or None,
            label=parts[1] or None,
            description=parts[2] or None,
            qualifier=parts[3] or None,
            qualifier_label=parts[4] or None,
            qualifier_description=parts[5] or None,
            hardware=parts[6] or None,
            hardware_label=parts[7] or None,
            hardware_description=parts[8] or None,
            doi=[options['DOI'], parts[9]] if parts[9] else None,
            url=[options['URL'], parts[10]] if parts[10] else None,
            parameters=parameters or None,
        )


@dataclass
class ProcessStep(QueryBatch):
    '''Relations of a Process Step entity from MaRDI/Wikidata.'''

    input_data_set: list[Relatant] = field(default_factory=list)
    output_data_set: list[Relatant] = field(default_factory=list)
    uses_algorithm: list[ProcessStepUsage] = field(default_factory=list)
    uses_method: list[ProcessStepUsage] = field(default_factory=list)
    field_of_work: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'ProcessStep':
        '''Parse one SPARQL result row into a ProcessStep instance.'''
        return cls(
            input_data_set=split_value(
                data=data, key='input_data_set', transform=Relatant.from_query
            ),
            output_data_set=split_value(
                data=data, key='output_data_set', transform=Relatant.from_query
            ),
            uses_algorithm=split_value(
                data=data, key='uses_algorithm', transform=ProcessStepUsage.from_query
            ),
            uses_method=split_value(
                data=data, key='uses_method', transform=ProcessStepUsage.from_query
            ),
            field_of_work=split_value(
                data=data, key='field_of_work', transform=Relatant.from_query
            ),
            publications=split_value(
                data=data, key='publication', transform=Relatant.from_query
            ),
        )


@dataclass
class CpuEntry:
    '''One CPU type on a hardware entity, with count information.'''
    id: Optional[str]
    label: Optional[str]
    description: Optional[str]
    count: Optional[str]

    @classmethod
    def from_query(cls, raw: str) -> 'CpuEntry':
        '''Parse a 4-field ``||``-delimited string into a CpuEntry instance.'''
        parts = raw.split(' || ')
        while len(parts) < 4:
            parts.append('')
        return cls(
            id=parts[0] or None,
            label=parts[1] or None,
            description=parts[2] or None,
            count=parts[3] or None,
        )


@dataclass
class Cpu:
    '''Number of processor cores for a CPU entity.'''
    cores: Optional[str] = None

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, Cpu]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls(
                cores=row.get('cores', {}).get('value') or None
            )
            for row in raw_data
            if row.get('qid', {}).get('value')
        }


@dataclass
class Hardware(QueryBatch):
    '''Node/core counts and CPU relations of a Hardware entity.'''

    nodes: Optional[str] = None
    cpu: list[CpuEntry] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'Hardware':
        '''Parse one SPARQL result row into a Hardware instance.'''
        return cls(
            nodes=data.get('number_of_nodes', {}).get('value') or None,
            cpu=split_value(data=data, key='cpu', transform=CpuEntry.from_query),
            publications=split_value(
                data=data, key='publication', transform=Relatant.from_query
            ),
        )


@dataclass
class Workflow(QueryBatch):
    '''Top-level metadata of an Interdisciplinary Workflow entity from MaRDI Portal.'''

    research_objective: list[str] = field(default_factory=list)
    procedure: list[str] = field(default_factory=list)
    mathematical: Optional[str] = None
    mathematical_comment: Optional[str] = None
    runtime: Optional[str] = None
    runtime_comment: Optional[str] = None
    result: Optional[str] = None
    result_comment: Optional[str] = None
    originalplatform: Optional[str] = None
    originalplatform_comment: Optional[str] = None
    otherplatform: Optional[str] = None
    otherplatform_comment: Optional[str] = None
    transferable: Optional[str] = None
    transferable_comment: list[str] = field(default_factory=list)
    uses_model: list[str] = field(default_factory=list)
    contains_process_step: list[Relatant] = field(default_factory=list)
    contains_workflow: list[Relatant] = field(default_factory=list)
    contained_in_workflow: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'Workflow':
        '''Parse one SPARQL result row into a Workflow instance.'''
        def _split(key):
            raw = data.get(key, {}).get('value', '')
            return [v.strip() for v in raw.split(' <|> ') if v.strip()] if raw else []

        def _val(key):
            return data.get(key, {}).get('value') or None

        return cls(
            research_objective=_split('research_objective'),
            procedure=_split('procedure'),
            mathematical=_val('mathematical'),
            mathematical_comment=_val('mathematical_comment'),
            runtime=_val('runtime'),
            runtime_comment=_val('runtime_comment'),
            result=_val('result'),
            result_comment=_val('result_comment'),
            originalplatform=_val('originalplatform'),
            originalplatform_comment=_val('originalplatform_comment'),
            otherplatform=_val('otherplatform'),
            otherplatform_comment=_val('otherplatform_comment'),
            transferable=_val('transferable'),
            transferable_comment=_split('transferable_comment'),
            uses_model=_split('uses_model'),
            contains_process_step=split_value(
                data=data, key='contains_process_step', transform=Relatant.from_query
            ),
            contains_workflow=split_value(
                data=data, key='contains_workflow', transform=Relatant.from_query
            ),
            contained_in_workflow=split_value(
                data=data, key='contained_in_workflow', transform=Relatant.from_query
            ),
            publications=split_value(
                data=data, key='publication', transform=Relatant.from_query
            ),
        )


@dataclass
class DataSet(QueryBatch):
    '''Metadata and relations of a Data Set entity from MaRDI/Wikidata.'''

    size: list = field(default_factory=list)
    file_format: Optional[str] = None
    binary_or_text: Optional[str] = None
    proprietary: Optional[str] = None
    to_publish: list = field(default_factory=list)
    to_archive: list = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'DataSet':
        '''Parse one SPARQL result row into a DataSet instance.'''
        options = get_options()

        return cls(
            size=get_size(data, options),
            file_format=data.get('file_format', {}).get('value'),
            binary_or_text=(
                options[data['binary_or_text']['value']]
                if data.get('binary_or_text', {}).get('value') else ''
            ),
            proprietary=(
                options[data['proprietary']['value']]
                if data.get('proprietary', {}).get('value') else ''
            ),
            to_publish=get_option_text_pair(data, options, 'publish', 'DOI'),
            to_archive=get_option_text_pair(data, options, 'archive', 'end_time'),
            publications=split_value(
                data=data, key='publication', transform=Relatant.from_query
            ),
        )
