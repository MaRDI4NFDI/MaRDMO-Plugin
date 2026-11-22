'''Package-wide constants of MaRDMO.

Defines the RDMO base URI, catalog name slugs (:data:`CATALOG_MODEL_NAME` etc.),
derived catalog URIs and the shared section-name map (:data:`SECTION_MAP_BASE`).
Where a questionnaire value goes in the answers: :mod:`MaRDMO.rules`.
'''

from django.utils.translation import gettext_noop as N_


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
    # QLever (University of Freiburg): Wikidata, updated live; it answers the
    # class checks of the dropdowns much faster (#170)
    'qlever': 'https://qlever.dev/api/wikidata',
}

DOI_BASE_URL             = 'https://doi.org/'
SWMATH_BASE_URL          = 'https://www.swmath.org/software/'
MORWIKI_BASE_URL         = 'https://modelreduction.org/morwiki/'
QUDT_QUANTITYKIND_URL    = 'https://qudt.org/vocab/quantitykind/'
QUDT_CONSTANT_URL        = 'https://qudt.org/vocab/constant/'
ORCID_BASE_URL           = 'https://orcid.org/'
ZBMATH_AUTHOR_BASE_URL   = 'https://zbmath.org/authors/?q=ai:'
ISSN_BASE_URL            = 'http://www.issn.cc/'

# TeX check of the production MaRDI Portal (same texvc as the export); used for
# all instances, since the check does not depend on the target portal's data
TEX_CHECK_URL            = 'https://portal.mardi4nfdi.de/w/rest.php/math/v0/check/tex'

#MaRDMO Section Mapt (Base)
SECTION_MAP_BASE = {
    'model':       N_('Mathematical Model'),
    'task':        N_('Computational Task'),
    'formulation': N_('Formula'),
    'quantity':    N_('Quantity [Kind]'),
    'field':       N_('Academic Discipline'),
    'algorithm':   N_('Algorithm'),
    'software':    N_('Software'),
    'benchmark':   N_('Benchmark'),
    'publication': N_('Publication'),
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
# Looked up by option, not by position (see properties.find_reference).
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
