'''The search catalog, as MaRDMO knows it: it searches the MaRDI Portal, it documents nothing (#198).'''
from ..core.catalogs import SEARCH, Catalog, Registration

CATALOG_SEARCH_NAME = 'mardmo-search-catalog'

REGISTRATION = Registration(
    catalogs=(
        Catalog(CATALOG_SEARCH_NAME, SEARCH, None, 'MaRDMO/preview_search.html'),
    ),
    questions={'search': 'search/data/questions.json'},
)
'''The search catalog's declaration.'''
