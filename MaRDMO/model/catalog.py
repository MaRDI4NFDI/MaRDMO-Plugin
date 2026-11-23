'''The model catalogs, as MaRDMO knows them: the full catalog and the basics (#198).'''
from ..core.catalogs import MODEL, Catalog, Registration
from ..core.constants import BASE_URI
from ..validators import validate_qudt_id, validate_short_description, validate_single_line
from .validators import validate_properties

CATALOG_MODEL_NAME = 'mardmo-model-catalog'
CATALOG_MODEL_BASICS_NAME = 'mardmo-model-basics-catalog'
CATALOG_MODEL = f'{BASE_URI}questions/{CATALOG_MODEL_NAME}'
CATALOG_MODEL_BASICS = f'{BASE_URI}questions/{CATALOG_MODEL_BASICS_NAME}'

REGISTRATION = Registration(
    catalogs=(
        Catalog(CATALOG_MODEL_NAME, MODEL, 'model', 'MaRDMO/preview_model.html',
                'MaRDMO.model.worker.PrepareModel', 'MaRDMO.model.checks.ModelChecks'),
        Catalog(CATALOG_MODEL_BASICS_NAME, MODEL, 'model', 'MaRDMO/preview_model_basics.html',
                'MaRDMO.model.worker.PrepareModel', 'MaRDMO.model.checks.ModelChecks', subset=True),
    ),
    questions={'model': 'model/data/questions.json'},
    information='MaRDMO.model.handlers.Information',
    handlers={
        ('Research Field', 'ID'): 'field',
        ('Research Problem', 'ID'): 'problem',
        ('Quantity', 'ID'): 'quantity',
        ('Mathematical Formulation', 'ID'): 'formulation',
        ('Task', 'ID'): 'task',
        ('Mathematical Model', 'ID'): 'model',
    },
    relations=(
        ('Task', 'QRelatant'),
        ('Task', 'MFRelatant'),
        ('Mathematical Formulation', 'Element Quantity'),
        ('Quantity', 'Element Quantity'),
        ('Mathematical Model', 'MFRelatant'),
        ('Mathematical Model', 'Assumption'),
        ('Task', 'Assumption'),
        ('Mathematical Formulation', 'Assumption'),
        ('Mathematical Formulation', 'MFRelatant'),
        ('Research Problem', 'RFRelatant'),
        ('Mathematical Model', 'RPRelatant'),
        ('Mathematical Model', 'TRelatant'),
    ),
    validators={
        validate_short_description: [
            ('Research Field', 'Description'),
            ('Research Problem', 'Description'),
            ('Quantity', 'Description'),
            ('Mathematical Formulation', 'Description'),
            ('Task', 'Description'),
            ('Mathematical Model', 'Description'),
        ],
        validate_single_line: [
            ('Research Field', 'Long Description'),
            ('Research Problem', 'Long Description'),
            ('Quantity', 'Long Description'),
            ('Mathematical Formulation', 'Long Description'),
            ('Task', 'Long Description'),
            ('Mathematical Model', 'Long Description'),
            ('Mathematical Formulation', 'Reference'),
        ],
        validate_properties: [
            ('Mathematical Model', 'Properties'),
            ('Mathematical Formulation', 'Properties'),
            ('Quantity', 'Properties'),
            ('Task', 'Properties'),
        ],
        validate_qudt_id: [
            ('Quantity', 'Reference'),
        ],
    },
    targets='MaRDMO.model.constants.get_uri_prefix_map',
    fills={
        'AD':  ('Research Field',          '_fill_field_batch'),
        'RP':  ('Research Problem',        '_fill_problem_batch'),
        'CT':  ('Task',                    '_fill_task_batch'),
        'F':   ('Mathematical Formulation','_fill_formulation_batch'),
        'QQK': ('Quantity',                '_fill_quantity_batch'),
    },
    routing=(
        {
            'props': 'P2ME',
            'classes': [
                'mathematical model', 'computational task', 'formula',
                'research problem', 'academic discipline', 'quantity', 'kind of quantity',
            ],
            'mapping': 'publication_mapping',
            'relation': 'P2ME',
            'relatant': 'ModelEntityRelatant',
        },
    ),
)
'''The model catalogs' declaration.'''
