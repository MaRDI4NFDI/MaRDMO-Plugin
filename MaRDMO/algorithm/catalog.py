'''The algorithm catalog, as MaRDMO knows it (#198).'''
from ..catalogs import ALGORITHM, Catalog, Registration
from ..constants import BASE_URI

CATALOG_ALGORITHM_NAME = 'mardmo-algorithm-catalog'
CATALOG_ALGORITHM = f'{BASE_URI}questions/{CATALOG_ALGORITHM_NAME}'

REGISTRATION = Registration(
    catalogs=(
        Catalog(CATALOG_ALGORITHM_NAME, ALGORITHM, 'algorithm', 'MaRDMO/preview_algorithm.html',
                'MaRDMO.algorithm.worker.PrepareAlgorithm', 'run_algorithm'),
    ),
    questions={'algorithm': 'algorithm/data/questions.json'},
)
'''The algorithm catalog's declaration.'''
