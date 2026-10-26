'''Compile-time constants and configuration builders for the Algorithm catalog.

Centralises the property URIs, relation definitions, and question/item
mappings that the algorithm documentation sub-package needs at runtime.
Values are loaded once from the RDMO database via the
``getters`` helpers and then referenced by handlers, providers, and workers.

Provides:

- ``get_relations()``      — returns the full relation-definition dict for algorithms
- ``get_uri_prefix_map()`` — returns the ``{prefix: URI}`` map used to expand compact IDs
- Module-level constants built from the above (``RELATIONS``, ``URI_PREFIX_MAP``, etc.)
'''

from ..constants import ALGORITHM_PROPS, BASE_URI, SECTION_MAP_BASE
from ..getters import get_mathalgodb, get_properties, get_questions
from ..publication.constants import get_publication_relations

#Dictionary for internal / external section names
SECTION_MAP = {**SECTION_MAP_BASE, 'problem': 'Algorithmic Task'}

# Dictionary with list of property names
PROPS = {
    **ALGORITHM_PROPS,
    'P2B':     ['manifests'],
    'Problem': ['specializes', 'specialized_by'],
}

# Same order as the options in the questionnaire: the list position is
# used as collection_index when imported references are stored
software_reference_ids = [
    'DOI',
    'SWMATH',
    'DESCRIPTION_URL',
    'SOURCECODE_URL',
]

# Same order as the options in the questionnaire: the list position is
# used as collection_index when imported references are stored
benchmark_reference_ids = [
    'DOI',
    'MORWIKI',
    'DESCRIPTION_URL',
    'SOURCECODE_URL',
]

# Relations
def get_relations():
    '''Build the relation mapping for the Algorithm Documentation.

    Maps each MathAlgoDB relation URL to the corresponding Wikibase property
    (and optional qualifier item or direction string) used when writing
    statements to the MaRDI Portal.

    Returns:
        Dict mapping MathAlgoDB relation URL strings to ``[property(, qualifier)]``
        lists; qualifier is either a Wikibase item ID or ``'forward'``/``'backward'``.
    '''
    mathalgodb = get_mathalgodb()
    properties = get_properties()
    relations = {
        **get_publication_relations(),
        # Map MathModDB Relation on Wikibase Property + Qualifier Item
        mathalgodb.get(key='manifests')['url']: [
            properties['manifestation of']
        ],
        mathalgodb.get(key='solves')['url']: [
            properties['solved by']
        ],
        mathalgodb.get(key='tested_by')['url']: [
            properties['tested by']
        ],
        mathalgodb.get(key='implemented_by')['url']: [
            properties['implemented by']
        ],
        # Map MathModDB Relation on Wikibase Property + Direction
        mathalgodb.get(key='specialized_by')['url']: [
            properties['specialized by'],
            'forward'
        ],
        mathalgodb.get(key='specializes')['url']: [
            properties['specialized by'],
            'backward'
        ],
        mathalgodb.get(key='has_component')['url']: [
            properties['has part(s)'],
            'forward'
        ],
        mathalgodb.get(key='component_of')['url']: [
            properties['has part(s)'],
            'backward'
        ],
        mathalgodb.get(key='has_subclass')['url']: [
            properties['subclass of'],
            'backward'
        ],
        mathalgodb.get(key='subclass_of')['url']: [
            properties['subclass of'],
            'forward'
        ],
        mathalgodb.get(key='related_to')['url']: [
            properties['similar to'],
            'forward'
        ],
    }
    return relations

# URI PREFIX Map
def get_uri_prefix_map():
    '''Build the attribute-URI → section config mapping for the Algorithm Documentation.

    Maps each relation attribute URI to the corresponding questionnaire section
    metadata needed to add or hydrate the related entity.

    Returns:
        Dict mapping full RDMO attribute URI strings to dicts with keys
        ``question_set``, ``question_id``, and ``prefix``.
    '''
    questions = get_questions('algorithm')
    uri_prefix_map = {
        f'{BASE_URI}{questions["Problem"]["BRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Benchmark"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Benchmark"]["ID"]["uri"]}',
            "prefix": "B"
        },
        f'{BASE_URI}{questions["Software"]["BRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Benchmark"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Benchmark"]["ID"]["uri"]}',
            "prefix": "B"
        },
        f'{BASE_URI}{questions["Algorithm"]["PRelatant"]["uri"]}': {
            "question_set": f'{BASE_URI}{questions["Problem"]["uri"]}',
            "question_id": f'{BASE_URI}{questions["Problem"]["ID"]["uri"]}',
            "prefix": "AT"
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

# Parameter for Entity relations
preview_relations = [
    {
        "from_idx": "algorithm",
        "to_idx": "problem",
        "relation": None,
        "old_name": "PRelatant",
        "new_name": "RelationP",
        "encryption": "AT"
    },
    {
        "from_idx": "algorithm",
        "to_idx": "software",
        "relation": None,
        "old_name": "SRelatant",
        "new_name": "RelationS",
        "encryption": "S"
    },
    {
        "from_idx": "algorithm",
        "to_idx": "algorithm",
        "relation": "IntraClassRelation",
        "old_name": "IntraClassElement",
        "new_name": "RelationA",
        "encryption": "A"
    },
    {
        "from_idx": "problem",
        "to_idx": "benchmark",
        "relation": None,
        "old_name": "BRelatant",
        "new_name": "RelationB",
        "encryption": "B"
    },
    {
        "from_idx": "problem",
        "to_idx": "problem",
        "relation": "IntraClassRelation",
        "old_name": "IntraClassElement",
        "new_name": "RelationP",
        "encryption": "AT"
    },
    {
        "from_idx": "software",
        "to_idx": "benchmark",
        "relation": None,
        "old_name": "BRelatant",
        "new_name": "RelationB",
        "encryption": "B"
    },
    {
        "from_idx": "software",
        "to_idx": "software",
        "relation": None,
        "old_name": "dependency",
        "new_name": "RelationS",
        "encryption": "S"
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
            "benchmark", "software"
        ],
        "relation": "P2BS",
        "old_name": "BSRelatant",
        "new_name": "RelationBS",
        "encryption": ["B", "S"],
        "mapping": "publication",
    }
]
