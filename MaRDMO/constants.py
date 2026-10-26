'''Package-wide constants and the answer-routing flag map for MaRDMO.

Defines the RDMO base URI, catalog name slugs (:data:`CATALOG_MODEL_NAME` etc.),
derived catalog URIs, the shared section-name map (:data:`SECTION_MAP_BASE`),
and :data:`flag_dict` — a mapping from five-tuple boolean flags to the
corresponding :mod:`~MaRDMO.rules` function used by
:func:`~MaRDMO.getters.get_answers` to route each questionnaire value into
the correct position in the answers dict.
'''

from . import rules

#RDMO BASE URI
BASE_URI = 'https://rdmo.mardi4nfdi.de/terms/'

# MaRDMO Catalog name slugs
CATALOG_MODEL_NAME        = 'mardmo-model-catalog'
CATALOG_MODEL_BASICS_NAME = 'mardmo-model-basics-catalog'
CATALOG_ALGORITHM_NAME    = 'mardmo-algorithm-catalog'
CATALOG_WORKFLOW_NAME     = 'mardmo-interdisciplinary-workflow-catalog'

# MaRDMO Catalog URIs
CATALOG_MODEL        = f'{BASE_URI}questions/{CATALOG_MODEL_NAME}'
CATALOG_MODEL_BASICS = f'{BASE_URI}questions/{CATALOG_MODEL_BASICS_NAME}'
CATALOG_ALGORITHM    = f'{BASE_URI}questions/{CATALOG_ALGORITHM_NAME}'
CATALOG_WORKFLOW     = f'{BASE_URI}questions/{CATALOG_WORKFLOW_NAME}'

# Wikidata endpoint URLs (internal — not user-configurable)
WIKIDATA = {
    'uri':    'https://www.wikidata.org',
    'entity': 'https://www.wikidata.org/entity/',
    'api':    'https://www.wikidata.org/w/api.php',
    'sparql': 'https://query-main.wikidata.org/sparql',
}

DOI_BASE_URL             = 'https://doi.org/'
SWMATH_BASE_URL          = 'https://www.swmath.org/software/'
MORWIKI_BASE_URL         = 'https://modelreduction.org/morwiki/'
QUDT_QUANTITYKIND_URL    = 'https://qudt.org/vocab/quantitykind/'
QUDT_CONSTANT_URL        = 'https://qudt.org/vocab/constant/'
ORCID_BASE_URL           = 'https://orcid.org/'
ZBMATH_AUTHOR_BASE_URL   = 'https://zbmath.org/authors/?q=ai:'
ISSN_BASE_URL            = 'http://www.issn.cc/'

# Mapping from catalog slug to preview template
CATALOG_TEMPLATE_MAP = {
    CATALOG_MODEL_NAME:        'MaRDMO/modelTemplate.html',
    CATALOG_MODEL_BASICS_NAME: 'MaRDMO/modelTemplate-basics.html',
    CATALOG_ALGORITHM_NAME:    'MaRDMO/algorithmTemplate.html',
    CATALOG_WORKFLOW_NAME:     'MaRDMO/workflowTemplate.html',
}

#MaRDMO Section Mapt (Base)
SECTION_MAP_BASE = {
    'model':       'Mathematical Model',
    'task':        'Computational Task',
    'formulation': 'Formula',
    'quantity':    'Quantity [Kind]',
    'field':       'Academic Discipline',
    'algorithm':   'Algorithm',
    'software':    'Software',
    'benchmark':   'Benchmark',
    'publication': 'Publication',
}

ALGORITHM_PROPS = {
    'A2P':       ['solves'],
    'A2S':       ['implemented_by'],
    'Algorithm': ['has_component', 'component_of', 'has_subclass', 'subclass_of', 'related_to'],
}

SOFTWARE_PROPS = {
    'S2PL': ['programmed_in'],
    'S2DP': ['depends_on_software'],
    'S2B':  ['tested_by'],
}

# Export mapping of reference answers: (option key, portal property, datatype).
# Looked up by option, not by position (see helpers.find_reference).
SOFTWARE_REFERENCES = (
    ('DOI',             'DOI',                        'external-id'),
    ('SWMATH',          'swMath work ID',             'external-id'),
    ('SOURCECODE_URL',  'source code repository URL', 'URL'),
    ('DESCRIPTION_URL', 'described at URL',           'URL'),
)
BENCHMARK_REFERENCES = (
    ('DOI',             'DOI',                        'external-id'),
    ('MORWIKI',         'MORwiki ID',                 'external-id'),
    ('SOURCECODE_URL',  'source code repository URL', 'URL'),
    ('DESCRIPTION_URL', 'described at URL',           'URL'),
)

# Same order as the options in the questionnaire: the list position is
# used as collection_index when imported references are stored
software_reference_ids = [
    'DOI',
    'SWMATH',
    'DESCRIPTION_URL',
    'SOURCECODE_URL',
]

# Tuple fields: (set_prefix, set_index, collection_index, external_id, option_text)
flag_dict = {
    (False, False, False, False, False): rules.rule_0,
    (True, False, False, False, False): rules.rule_1,
    (False, True, False, False, False): rules.rule_2,
    (True, True, False, False, False): rules.rule_3,
    (False, True, True, False, False): rules.rule_4,
    (True, False, True, False, False): rules.rule_5,
    (True, True, True, False, False): rules.rule_19,
    (True, True, True, False, True): rules.rule_6,
    (True, False, False, False, True): rules.rule_7,
    (False, True, False, False, True): rules.rule_8,
    (False, False, False, True, False): rules.rule_9,
    (False, False, True, False, False): rules.rule_10,
    (False, False, True, True, False): rules.rule_11,
    (False, True, False, True, False): rules.rule_12,
    (True, True, False, True, False): rules.rule_13,
    (True, False, True, True, False): rules.rule_14,
    (True, True, True, True, False): rules.rule_15,
    (True, True, False, False, True): rules.rule_16,
    (True, False, True, False, True): rules.rule_17,
    (False, True, True, False, True): rules.rule_18,
}
