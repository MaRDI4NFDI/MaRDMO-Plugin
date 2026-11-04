'''Compile-time constants and configuration builders for the Workflow catalog.

Centralises the property URIs, question/item mappings, and publication-order
definitions used by the workflow documentation sub-package at runtime.
Values are loaded once from the RDMO database via the ``getters`` helpers
and then referenced by handlers, providers, and workers.

Provides:

- ``get_uri_prefix_map()`` — returns the ``{prefix: URI}`` map used to expand compact IDs
- ``order_to_publish()``   — returns the ordered list of workflow attributes for portal export
- Module-level constants built from the above
'''

from ..constants import BASE_URI
from ..getters import get_mathmoddb, get_options, get_properties, get_questions
from ..publication.constants import get_publication_relations

SECTION_MAP = {
    'workflow':    'Interdisciplinary Workflow',
    'processstep': 'Process Step',
    'algorithm':   'Algorithm',
    'software':    'Software',
    'hardware':    'Hardware',
    'dataset':     'Data Set',
    'publication': 'Publication',
}

# Same order as the options in the questionnaire: the list position is
# used as collection_index when imported references are stored
software_reference_ids = [
    'DOI',
    'SWMATH',
    'DESCRIPTION_URL',
    'SOURCECODE_URL',
]

# URI PREFIX Map
def get_uri_prefix_map():
    '''Build the attribute-URI → section config mapping for the Workflow Documentation.

    Maps each relation attribute URI to the corresponding questionnaire section
    metadata needed to add or hydrate the related entity.

    Returns:
        Dict mapping full RDMO attribute URI strings to dicts with keys
        ``question_set``, ``question_id``, and ``prefix``.
    '''
    questions = get_questions('workflow')
    uri_prefix_map = {
        f'{BASE_URI}{questions["Process Step"]["Algorithm"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Algorithm"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Algorithm"]["ID"]["uri"]}',
            "prefix": "A"
        },
        f'{BASE_URI}{questions["Process Step"]["Hardware"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Hardware"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Hardware"]["ID"]["uri"]}',
            "prefix": "HW"
        },
        f'{BASE_URI}{questions["Process Step"]["Input"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Data Set"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Data Set"]["ID"]["uri"]}',
            "prefix": "DS"
        },
        f'{BASE_URI}{questions["Process Step"]["Output"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Data Set"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Data Set"]["ID"]["uri"]}',
            "prefix": "DS"
        },
        f'{BASE_URI}{questions["Workflow"]["PSRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Process Step"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Process Step"]["ID"]["uri"]}',
            "prefix": "PS"
        },
        f'{BASE_URI}{questions["Process Step"]["Software"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Software"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Software"]["ID"]["uri"]}',
            "prefix": "S"
        },
        f'{BASE_URI}{questions["Algorithm"]["SRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Software"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Software"]["ID"]["uri"]}',
            "prefix": "S"
        },
        f'{BASE_URI}{questions["Software"]["Dependency"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Software"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Software"]["ID"]["uri"]}',
            "prefix": "S"
        },
    }
    return uri_prefix_map


def get_relations():
    '''Return the workflow relation mapping.

    Extends the shared publication-role mapping with the workflow intra-class
    relations (contains / contained in) from MathModDB.
    '''
    mathmoddb  = get_mathmoddb()
    properties = get_properties()
    return {
        **get_publication_relations(),
        mathmoddb.get(key='contains_workflow')['url']: [
            properties['contains'],
            'forward'
        ],
        mathmoddb.get(key='contained_in_workflow')['url']: [
            properties['contains'],
            'backward'
        ],
    }


# Dictionary with list of property names
PROPS = {
    'PS2IDS': ['input_data_set'],
    'PS2ODS': ['output_data_set'],
    'PS2A':   ['uses_algorithm'],
    'PS2M':   ['uses_method'],
    'PS2F':   ['field_of_work'],
    'IW2IW':  ['contains_workflow', 'contained_in_workflow'],
}

# Order of toPublish Answers
def order_to_publish():
    '''Build an ordered mapping of publishing option keys to ``(rank, option_value)`` tuples.

    Returns:
        Dict ``{"Yes": (0, …), "doi": (1, …), "url": (2, …), "No": (3, …)}``
        where values are resolved RDMO option strings.
    '''
    options = get_options()
    order = {
        'Yes': (0, options['Yes']),
        'doi': (1, options['DOI']),
        'url': (2, options['URL']),
        'No': (3, options['No'])
        }
    return order

#Dictionary For Reproducibility
REPRODUCIBILITY = {
    'mathematical':    'mathematically reproducible research workflow',
    'runtime':         'runtime reproducible research workflow',
    'result':          'result reproducible research workflow',
    'originalplatform': 'original platform reproducible research workflow',
    'otherplatform':   'cross-platform reproducible research workflow',
}

IRREPRODUCIBILITY = {
    'mathematical':    'mathematically irreproducible research workflow',
    'runtime':         'runtime irreproducible research workflow',
    'result':          'result irreproducible research workflow',
    'originalplatform': 'original platform irreproducible research workflow',
    'otherplatform':   'cross-platform irreproducible research workflow',
}

# Parameter for Entity relations
preview_relations = [
    {
        "from_idx": "workflow",
        "to_idx":   "workflow",
        "relation":  "IntraClassRelation",
        "old_name":  "IntraClassElement",
        "new_name":  "RelationWF",
        "encryption": "IW",
        "assumption":  False,
        "grouped":     False,
        "mapping":     "mathmoddb",
    },
    {
        "from_idx": "workflow",
        "to_idx": "processstep",
        "relation": None,
        "old_name": "PSRelatant",
        "new_name": "RelationPS",
        "encryption": "PS",
        "assumption": False,
        "grouped": False,
    },
    {
        "from_idx": "processstep",
        "to_idx": "dataset",
        "relation": None,
        "old_name": "IDSRelatant",
        "new_name": "RelationIDS",
        "encryption": "DS",
        "assumption": False,
        "grouped": False,
    },
    {
        "from_idx": "processstep",
        "to_idx": "dataset",
        "relation": None,
        "old_name": "ODSRelatant",
        "new_name": "RelationODS",
        "encryption": "DS",
        "assumption": False,
        "grouped": False,
    },
    {
        "from_idx": "processstep",
        "to_idx": "algorithm",
        "relation": None,
        "old_name": "ARelatant",
        "new_name": "RelationA",
        "encryption": "A",
        "assumption": False,
        "grouped": True,
    },
    {
        "from_idx": "processstep",
        "to_idx": "software",
        "relation": None,
        "old_name": "SRelatant",
        "new_name": "RelationS",
        "encryption": "S",
        "assumption": False,
        "grouped": True,
    },
    {
        "from_idx": "processstep",
        "to_idx": "method",
        "relation": None,
        "old_name": "MRelatant",
        "new_name": "RelationM",
        "encryption": "M",
        "assumption": False,
        "grouped": True,
    },
    {
        "from_idx": "processstep",
        "to_idx": "instrument",
        "relation": None,
        "old_name": "IRelatant",
        "new_name": "RelationI",
        "encryption": "I",
        "assumption": False,
        "grouped": True,
    },
    {
        "from_idx": "processstep",
        "to_idx": "hardware",
        "relation": None,
        "old_name": "HRelatant",
        "new_name": "RelationH",
        "encryption": "HW",
        "assumption": False,
        "grouped": True,
    },
    {
        "from_idx": "algorithm",
        "to_idx": "software",
        "relation": None,
        "old_name": "SRelatant",
        "new_name": "RelationS",
        "encryption": "S",
        "assumption": False,
        "grouped": False,
    },
    {
        "from_idx": "software",
        "to_idx": "software",
        "relation": None,
        "old_name": "dependency",
        "new_name": "RelationS",
        "encryption": "S",
        "assumption": False,
        "grouped": False,
    },
    {
        "from_idx": "publication",
        "to_idx": "algorithm",
        "relation": "P2A",
        "old_name": "ARelatant",
        "new_name": "RelationA",
        "encryption": "A",
        "mapping": "publication",
    },
    {
        "from_idx": "publication",
        "to_idx": [
            "hardware", "software"
        ],
        "relation": "P2BS",
        "old_name": "HSRelatant",
        "new_name": "RelationHS",
        "encryption": ["HW", "S"],
        "mapping": "publication",
    },
    {
        "from_idx": "publication",
        "to_idx": [
            "workflow", "processstep", "dataset"
        ],
        "relation": "P2E",
        "old_name": "EntityRelatant",
        "new_name": "RelationP",
        "encryption": ["IW", "PS", "DS"],
        "assumption": False,
        "mapping": "publication",
    },
]
