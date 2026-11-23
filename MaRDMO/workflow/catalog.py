'''The interdisciplinary workflow catalog, as MaRDMO knows it (#198).'''
from ..core.catalogs import WORKFLOW, Catalog, Registration
from ..core.constants import BASE_URI
from ..validators import (
    validate_archive_year,
    validate_count,
    validate_data_size,
    validate_doi,
    validate_reference,
    validate_short_description,
    validate_single_line,
)

CATALOG_WORKFLOW_NAME = 'mardmo-interdisciplinary-workflow-catalog'
CATALOG_WORKFLOW = f'{BASE_URI}questions/{CATALOG_WORKFLOW_NAME}'

REGISTRATION = Registration(
    catalogs=(
        Catalog(CATALOG_WORKFLOW_NAME, WORKFLOW, 'workflow', 'MaRDMO/preview_workflow.html',
                'MaRDMO.workflow.worker.PrepareWorkflow', 'MaRDMO.workflow.checks.WorkflowChecks'),
    ),
    questions={'workflow': 'workflow/data/questions.json'},
    information='MaRDMO.workflow.handlers.Information',
    handlers={
        ('Workflow', 'ID'): 'workflow',
        ('Algorithm', 'ID'): 'algorithm',
        ('Workflow', 'Model'): 'model',
        ('Software', 'ID'): 'software',
        ('Hardware', 'ID'): 'hardware',
        ('Hardware', 'CPU'): 'processor_cores',
        ('Data Set', 'ID'): 'data_set',
        ('Process Step', 'ID'): 'process_step',
    },
    relations=(
        ('Process Step', 'Algorithm'),
        ('Process Step', 'Hardware'),
        ('Process Step', 'Input'),
        ('Process Step', 'Output'),
        ('Workflow', 'PSRelatant'),
        ('Process Step', 'Software'),
        ('Algorithm', 'SRelatant'),
        ('Software', 'Dependency'),
    ),
    validators={
        validate_short_description: [
            ('Workflow', 'Description'),
            ('Algorithm', 'Description'),
            ('Software', 'Description'),
            ('Hardware', 'Description'),
            ('Data Set', 'Description'),
            ('Process Step', 'Description'),
        ],
        validate_single_line: [
            ('Workflow', 'Long Description'),
            ('Workflow', 'Mathematical'),
            ('Workflow', 'Runtime'),
            ('Workflow', 'Result'),
            ('Workflow', 'Original Platform'),
            ('Workflow', 'Other Platform'),
        ],
        validate_reference: [
            ('Software', 'Reference'),
            ('Process Step', 'Software-Documentation'),
            ('Process Step', 'Method-Documentation'),
        ],
        validate_doi: [
            ('Data Set', 'To Publish'),
        ],
        validate_archive_year: [
            ('Data Set', 'To Archive'),
        ],
        validate_data_size: [
            ('Data Set', 'Size'),
        ],
        validate_count: [
            ('Hardware', 'Nodes'),
            ('Hardware', 'Number of CPU'),
            ('Hardware', 'Cores'),
        ],
    },
    targets='MaRDMO.workflow.constants.get_uri_prefix_map',
    fills={
        'A':  ('Algorithm',    '_fill_algorithm_batch'),
        'DS': ('Data Set',     '_fill_data_set_batch'),
        'S':  ('Software',     '_fill_software_batch'),
        'HW': ('Hardware',     '_fill_hardware_batch'),
        'PS': ('Process Step', '_fill_process_step_batch'),
    },
    routing=(
        {
            'props': 'P2A',
            'classes': ['algorithm'],
            'mapping': 'publication_mapping',
            'relation': 'P2A',
            'relatant': 'ARelatant',
        },
        {
            'props': 'P2BS',
            'classes': ['software', 'computer hardware'],
            'mapping': 'publication_mapping',
            'relation': 'P2BS',
            'relatant': 'HSRelatant',
        },
        {
            'props': 'P2IWE',
            'classes': ['research workflow', 'process step', 'data set'],
            'mapping': 'publication_mapping',
            'relation': 'P2IWE',
            'relatant': 'IWERelatant',
        },
    ),
)
'''The workflow catalog's declaration.'''
