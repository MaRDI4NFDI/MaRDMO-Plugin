'''Compile-time constants and configuration builders for the Model catalog.

Centralises the property URIs, relation definitions, and question/item
mappings that the model documentation sub-package needs at runtime.
Values are loaded once from the RDMO database via the ``getters`` helpers
and then referenced by handlers, providers, and workers.

Provides:

- ``get_relations()``       — returns the full relation-definition dict for mathematical models
- ``get_uri_prefix_map()``  — returns the ``{prefix: URI}`` map used to expand compact IDs
- Module-level constants built from the above (``RELATIONS``, ``URI_PREFIX_MAP``, etc.)
'''

from ..constants import BASE_URI, SECTION_MAP_BASE
from ..getters import get_items, get_mathmoddb, get_properties, get_questions
from ..publication.constants import get_publication_relations

# Data Properties Check
data_properties_check = [
    ('is_deterministic', 'is_stochastic'),
    ('is_dimensionless', 'is_dimensional'),
    ('is_dynamic', 'is_static'),
    ('is_linear', 'is_not_linear'),
    ('is_space_continuous', 'is_space_discrete'),
    ('is_time_continuous', 'is_time_discrete'),
    ('is_mathematical_constant', 'is_physical_constant'),
    ('is_mathematical_constant', 'is_chemical_constant'),
    ('is_physical_constant', 'is_chemical_constant'),
    ('is_ordinary_differential_equation', 'is_partial_differential_equation'),
    ('is_ordinary_differential_equation', 'is_stochastic_differential_equation'),
    ('is_ordinary_differential_equation', 'is_integro_differential_equation'),
    ('is_partial_differential_equation', 'is_stochastic_differential_equation'),
    ('is_partial_differential_equation', 'is_integro_differential_equation'),
    ('is_stochastic_differential_equation', 'is_integro_differential_equation'),
]

# Data Properties per Class
data_properties_per_class = {
    'model': [
        'is_linear', 'is_not_linear', 'is_dynamic', 'is_static',
        'is_deterministic', 'is_stochastic', 'is_dimensionless', 'is_dimensional',
        'is_time_continuous', 'is_time_discrete', 'is_space_continuous', 'is_space_discrete',
    ],
    'quantity': [
        'is_chemical_constant', 'is_mathematical_constant', 'is_physical_constant',
        'is_dynamic', 'is_static', 'is_deterministic', 'is_stochastic', 'is_dimensionless',
        'is_dimensional', 'is_time_continuous', 'is_time_discrete', 'is_space_continuous',
        'is_space_discrete'
    ],
    'formulation': [
        'is_linear', 'is_not_linear', 'is_dynamic', 'is_static', 'is_deterministic',
        'is_stochastic', 'is_dimensionless', 'is_dimensional', 'is_time_continuous',
        'is_time_discrete', 'is_space_continuous', 'is_space_discrete',
        'is_ordinary_differential_equation', 'is_partial_differential_equation',
        'is_stochastic_differential_equation', 'is_integro_differential_equation'
    ],
    'task': ['is_linear', 'is_not_linear', 'is_time_continuous', 'is_time_discrete',
             'is_space_continuous', 'is_space_discrete'
    ]
}

# Key-Item Map for Class-Independent Data Properties
INDEPENDENT_PROPERTIES = [
    ('is_ordinary_differential_equation',   'ordinary differential equation'),
    ('is_partial_differential_equation',    'partial differential equation'),
    ('is_stochastic_differential_equation', 'stochastic differential equation'),
    ('is_integro_differential_equation',    'integro-differential equation'),
    ('is_chemical_constant',                'chemical constant'),
    ('is_mathematical_constant',            'mathematical constant'),
    ('is_physical_constant',                'physical constant'),
]

# Key-Item Map for Class-Dependent Data Properties
DEPENDENT_PROPERTIES = [
    ('is_deterministic',     'deterministic'),
    ('is_stochastic',        'probabilistic'),
    ('is_dimensional',       'dimensional'),
    ('is_dimensionless',     'dimensionless'),
    ('is_dynamic',           'dynamic'),
    ('is_static',            'static'),
    ('is_linear',            'linear'),
    ('is_not_linear',        'nonlinear'),
    ('is_space_continuous',  'continuous-space'),
    ('is_space_discrete',    'discrete-space'),
    ('is_time_continuous',   'continuous-time'),
    ('is_time_discrete',     'discrete-time'),
]

# QUDT Reference IDs
qudt_reference_ids = [
    'qudt_quantitykind_id',
    'qudt_constant_id'
]

# Dictionary for internal / external section names
SECTION_MAP = {**SECTION_MAP_BASE, 'problem': 'Research Problem'}

# Dictionary with list of property names
props = {
    'T2MF': [
        'assumes',
        'contains_analytical_solution',
        'contains_governing_equation',
        'contains_computational_domain',
        'contains_weak_formulation',
        'contains_strong_formulation',
        'contains_formulation',
        'contains_boundary_condition',
        'contains_constraint_condition',
        'contains_coupling_condition',
        'contains_initial_condition',
        'contains_final_condition'
    ],
    'T2Q': [
        'contains_input',
        'contains_output',
        'contains_objective',
        'contains_parameter',
        'contains_constant'
    ],
    'RP2RF': [
        'contained_in_field'
    ],
    'MM2RP': [
        'models'
    ],
    'MM2T': [
        'used_by'
    ],
    'MM2MF': [
        'assumes',
        'contains_analytical_solution',
        'contains_governing_equation',
        'contains_computational_domain',
        'contains_weak_formulation',
        'contains_strong_formulation',
        'contains_formulation',
        'contains_boundary_condition',
        'contains_constraint_condition',
        'contains_coupling_condition',
        'contains_initial_condition',
        'contains_final_condition'
    ],
    'MF2MF': [
        'assumes',
        'contains_formulation',
        'contains_boundary_condition',
        'contains_constraint_condition',
        'contains_coupling_condition',
        'contains_initial_condition',
        'contains_final_condition'
    ],
    'Field': [
        "specialized_by",
        "specializes",
        "similar_to"
    ],
    'Problem': [
        "specialized_by",
        "specializes",
        "similar_to"
    ],
    'Model': [
        'specialized_by',
        'specializes',
        'discretized_by',
        'discretizes',
        'contained_in_model',
        'contains_model',
        'approximated_by',
        'approximates',
        'linearized_by',
        'linearizes',
        'similar_to',
        'has_weak_formulation',
        'is_weak_formulation_of'
    ],
    'Task': [
        'specialized_by',
        'specializes',
        'discretized_by',
        'discretizes',
        'contained_in_task',
        'contains_task',
        'approximated_by',
        'approximates',
        'linearized_by',
        'linearizes',
        'similar_to'
    ],
    'Formulation': [
        'specialized_by',
        'specializes',
        'discretized_by',
        'discretizes',
        'approximated_by',
        'approximates',
        'linearized_by',
        'linearizes',
        'nondimensionalized_by',
        'nondimensionalizes',
        'similar_to',
        'has_weak_formulation',
        'is_weak_formulation_of'
    ],
    'Quantity': [
        "specialized_by",
        "specializes",
        "approximated_by",
        "approximates",
        "discretized_by",
        "discretizes",
        "linearized_by",
        "linearizes",
        "nondimensionalized_by",
        "nondimensionalizes",
        "similar_to"
    ],
}

# URI mappings for quantity relations
relation_uris = {
    ("Quantity", "Quantity"): "Q2Q",
    ("QuantityKind", "QuantityKind"): "QK2QK",
    ("Quantity", "QuantityKind"): "Q2QK",
    ("QuantityKind", "Quantity"): "QK2Q",
}

# URI mappings for quantity relatants
relatant_uris = {
    ("Quantity", "Quantity"): "QQRelatant",
    ("QuantityKind", "QuantityKind"): "QKQKRelatant",
    ("Quantity", "QuantityKind"): "QQKRelatant",
    ("QuantityKind", "Quantity"): "QKQRelatant",
}

# Relations
def get_relations():
    '''Build the relation mapping for the Model Documentation.

    Maps each MathModDB relation URL to the corresponding Wikibase property
    (and optional qualifier item or direction string) used when writing
    statements to the MaRDI Portal.

    Returns:
        Dict mapping MathModDB relation URL strings to ``[property(, qualifier)]``
        lists; qualifier is either a Wikibase item ID or ``'forward'``/``'backward'``.
    '''
    mathmoddb  = get_mathmoddb()
    items      = get_items()
    properties = get_properties()
    relations = {
        **get_publication_relations(),
        # Map MathModDB Relation on Wikibase Property + Qualifier Item
        mathmoddb.get(key='assumes')['url']: [
            properties['assumes']
        ],
        mathmoddb.get(key='contains_boundary_condition')['url']: [
            properties['contains'],
            items['boundary condition']
        ],
        mathmoddb.get(key='contains_constraint_condition')['url']: [
            properties['contains'],
            items['constraint']
        ],
        mathmoddb.get(key='contains_coupling_condition')['url']: [
            properties['contains'],
            items['coupling condition']
        ],
        mathmoddb.get(key='contains_initial_condition')['url']: [
            properties['contains'],
            items['initial condition']
        ],
        mathmoddb.get(key='contains_final_condition')['url']: [
            properties['contains'],
            items['final condition']
        ],
        mathmoddb.get(key='contains_input')['url']: [
            properties['contains'],
            items['input']
        ],
        mathmoddb.get(key='contains_constant')['url']: [
            properties['contains'],
            items['constant']
        ],
        mathmoddb.get(key='contains_objective')['url']: [
            properties['contains'],
            items['objective function']
        ],
        mathmoddb.get(key='contains_output')['url']: [
            properties['contains'],
            items['output']
        ],
        mathmoddb.get(key='contains_parameter')['url']: [
            properties['contains'],
            items['parameter']
        ],
        mathmoddb.get(key='contains_analytical_solution')['url']: [
            properties['contains'],
            items['analytical solution']
        ],
        mathmoddb.get(key='contains_governing_equation')['url']: [
            properties['contains'],
            items['governing equation']
        ],
        mathmoddb.get(key='contains_computational_domain')['url']: [
            properties['contains'],
            items['computational domain']
        ],
        mathmoddb.get(key='contains_weak_formulation')['url']: [
            properties['contains'],
            items['weak formulation']
        ],
        mathmoddb.get(key='contains_strong_formulation')['url']: [
            properties['contains'],
            items['strong formulation']
        ],
        # Map MathModDB Relation on Wikibase Property + Direction
        mathmoddb.get(key='specialized_by')['url']: [
            properties['specialized by'],
            'forward'
        ],
        mathmoddb.get(key='specializes')['url']: [
            properties['specialized by'],
            'backward'
        ],
        mathmoddb.get(key='approximated_by')['url']: [
            properties['approximated by'],
            'forward'
        ],
        mathmoddb.get(key='approximates')['url']: [
            properties['approximated by'],
            'backward'
        ],
        mathmoddb.get(key='discretized_by')['url']: [
            properties['discretized by'],
            'forward'
        ],
        mathmoddb.get(key='discretizes')['url']: [
            properties['discretized by'],
            'backward'
        ],
        mathmoddb.get(key='linearized_by')['url']: [
            properties['linearized by'],
            'forward'
        ],
        mathmoddb.get(key='linearizes')['url']: [
            properties['linearized by'],
            'backward'
        ],
        mathmoddb.get(key='nondimensionalized_by')['url']: [
            properties['nondimensionalized by'],
            'forward'
        ],
        mathmoddb.get(key='nondimensionalizes')['url']: [
            properties['nondimensionalized by'],
            'backward'
        ],
        mathmoddb.get(key='contains')['url']: [
            properties['contains'],
            'forward'
        ],
        mathmoddb.get(key='contained_in')['url']: [
            properties['contains'],
            'backward'
        ],
        mathmoddb.get(key='similar_to')['url']: [
            properties['similar to'],
            'forward'
        ],
        mathmoddb.get(key='has_weak_formulation')['url']: [
            properties['has weak formulation'],
            'forward'
        ],
        mathmoddb.get(key='is_weak_formulation_of')['url']: [
            properties['has weak formulation'],
            'backward'
        ]
    }
    return relations

# Parameter for Entity relations
preview_relations = [
    {
        "from_idx": "model",
        "to_idx": "problem",
        "relation": None,
        "old_name": "RPRelatant",
        "new_name": "RelationRP",
        "encryption": "RP",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "model",
        "to_idx": "formulation",
        "relation": "MM2MF",
        "old_name": "MFRelatant",
        "new_name": "RelationMF",
        "encryption": "F",
        "formulation": True,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "model",
        "to_idx": "task",
        "relation": None,
        "old_name": "TRelatant",
        "new_name": "RelationT",
        "encryption": "CT",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "model",
        "to_idx": "model",
        "relation": "IntraClassRelation",
        "old_name": "IntraClassElement",
        "new_name": "RelationMM",
        "encryption": "MM",
        "formulation": False,
        "task": False,
        "assumption": True,
    },
    {
        "from_idx": "task",
        "to_idx": "formulation",
        "relation": "T2MF",
        "old_name": "MFRelatant",
        "new_name": "RelationMF",
        "encryption": "F",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "task",
        "to_idx": "quantity",
        "relation": "T2Q",
        "old_name": "QRelatant",
        "new_name": "RelationQQK",
        "encryption": "QQK",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "task",
        "to_idx": "task",
        "relation": "IntraClassRelation",
        "old_name": "IntraClassElement",
        "new_name": "RelationT",
        "encryption": "CT",
        "formulation": False,
        "task": True,
        "assumption": True,
    },
    {
        "from_idx": "formulation",
        "to_idx": "formulation",
        "relation": "MF2MF",
        "old_name": "MFRelatant",
        "new_name": "RelationMF1",
        "encryption": "F",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "formulation",
        "to_idx": "formulation",
        "relation": "IntraClassRelation",
        "old_name": "IntraClassElement",
        "new_name": "RelationMF2",
        "encryption": "F",
        "formulation": False,
        "task": False,
        "assumption": True,
    },
    {
        "from_idx": "quantity",
        "to_idx": "quantity",
        "relation": "Q2Q",
        "old_name": "QRelatant-Q",
        "new_name": "RelationQQ",
        "encryption": "QQK",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "quantity",
        "to_idx": "quantity",
        "relation": "QK2QK",
        "old_name": "QKRelatant-QK",
        "new_name": "RelationQKQK",
        "encryption": "QQK",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "quantity",
        "to_idx": "quantity",
        "relation": "Q2QK",
        "old_name": "QKRelatant-Q",
        "new_name": "RelationQQK",
        "encryption": "QQK",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "quantity",
        "to_idx": "quantity",
        "relation": "QK2Q",
        "old_name": "QRelatant-QK",
        "new_name": "RelationQKQ",
        "encryption": "QQK",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "field",
        "to_idx": "field",
        "relation": "IntraClassRelation",
        "old_name": "IntraClassElement",
        "new_name": "RelationRF",
        "encryption": "AD",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "problem",
        "to_idx": "field",
        "relation": None,
        "old_name": "RFRelatant",
        "new_name": "RelationRF",
        "encryption": "AD",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "problem",
        "to_idx": "problem",
        "relation": "IntraClassRelation",
        "old_name": "IntraClassElement",
        "new_name": "RelationRP",
        "encryption": "RP",
        "formulation": False,
        "task": False,
        "assumption": False,
    },
    {
        "from_idx": "publication",
        "to_idx": [
            "field", "problem", "model",
            "formulation", "quantity", "task",
        ],
        "relation": "P2E",
        "old_name": "EntityRelatant",
        "new_name": "RelationP",
        "encryption": ["RF", "RP", "MM", "F", "QQK", "CT"],
        "formulation": False,
        "task": False,
        "assumption": False,
        "mapping": "publication",
    },
]

preview_map_general = [
    # fromIDX, toIDX, entityOld, entityNew, enc
    ('model', 'formulation', 'assumption', 'assumptionMapped', 'F'),
    ('task', 'formulation', 'assumption', 'assumptionMapped', 'F'),
    ('formulation', 'formulation', 'assumption', 'assumptionMapped', 'F'),
]

preview_map_quantity = [
    # type
    ('formulation'),
    ('quantity'),
]

# URI PREFIX Map (I)
def get_uri_prefix_map():
    '''Build the attribute-URI → section config mapping for the Model Documentation.

    Maps each relation attribute URI (used as a trigger in the handler map) to
    the corresponding questionnaire section metadata needed to add or hydrate
    the related entity.

    Returns:
        Dict mapping full RDMO attribute URI strings to dicts with keys
        ``question_set`` (section root URI), ``question_id`` (ID field URI),
        and ``prefix`` (label prefix string, e.g. ``"AD"``).
    '''
    questions = get_questions('model')
    uri_prefix_map = {
        f'{BASE_URI}{questions["Task"]["QRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Quantity"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Quantity"]["ID"]["uri"]}',
            "prefix": "QQK"
        },
        f'{BASE_URI}{questions["Task"]["MFRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Mathematical Formulation"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Mathematical Formulation"]["ID"]["uri"]}',
            "prefix": "F"
        },
        f'{BASE_URI}{questions["Mathematical Formulation"]["Element Quantity"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Quantity"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Quantity"]["ID"]["uri"]}',
            "prefix": "QQK"
        },
        f'{BASE_URI}{questions["Quantity"]["Element Quantity"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Quantity"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Quantity"]["ID"]["uri"]}',
            "prefix": "QQK"
        },
        f'{BASE_URI}{questions["Mathematical Model"]["MFRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Mathematical Formulation"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Mathematical Formulation"]["ID"]["uri"]}',
            "prefix": "F"
        },
        f'{BASE_URI}{questions["Mathematical Model"]["Assumption"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Mathematical Formulation"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Mathematical Formulation"]["ID"]["uri"]}',
            "prefix": "F"
        },
        f'{BASE_URI}{questions["Task"]["Assumption"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Mathematical Formulation"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Mathematical Formulation"]["ID"]["uri"]}',
            "prefix": "F"
        },
        f'{BASE_URI}{questions["Mathematical Formulation"]["Assumption"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Mathematical Formulation"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Mathematical Formulation"]["ID"]["uri"]}',
            "prefix": "F"
        },
        f'{BASE_URI}{questions["Mathematical Formulation"]["MFRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Mathematical Formulation"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Mathematical Formulation"]["ID"]["uri"]}',
            "prefix": "F"
        },
        f'{BASE_URI}{questions["Research Problem"]["RFRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Research Field"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Research Field"]["ID"]["uri"]}',
            "prefix": "AD"
        },
        f'{BASE_URI}{questions["Mathematical Model"]["RPRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Research Problem"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Research Problem"]["ID"]["uri"]}',
            "prefix": "RP"
        },
        f'{BASE_URI}{questions["Mathematical Model"]["TRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Task"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Task"]["ID"]["uri"]}',
            "prefix": "CT"
        }
    }
    return uri_prefix_map
