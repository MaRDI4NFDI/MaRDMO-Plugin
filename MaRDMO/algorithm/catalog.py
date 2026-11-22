'''The algorithm catalog, as MaRDMO knows it (#198).'''
from ..catalogs import ALGORITHM, Catalog, Registration
from ..constants import BASE_URI
from ..validators import validate_reference, validate_short_description

CATALOG_ALGORITHM_NAME = 'mardmo-algorithm-catalog'
CATALOG_ALGORITHM = f'{BASE_URI}questions/{CATALOG_ALGORITHM_NAME}'

REGISTRATION = Registration(
    catalogs=(
        Catalog(CATALOG_ALGORITHM_NAME, ALGORITHM, 'algorithm', 'MaRDMO/preview_algorithm.html',
                'MaRDMO.algorithm.worker.PrepareAlgorithm', 'run_algorithm'),
    ),
    questions={'algorithm': 'algorithm/data/questions.json'},
    information='MaRDMO.algorithm.handlers.Information',
    handlers={
        ('Benchmark', 'ID'): 'benchmark',
        ('Software', 'ID'): 'software',
        ('Problem', 'ID'): 'problem',
        ('Algorithm', 'ID'): 'algorithm',
    },
    relations=(
        ('Problem', 'BRelatant'),
        ('Software', 'BRelatant'),
        ('Algorithm', 'PRelatant'),
        ('Algorithm', 'SRelatant'),
        ('Software', 'Dependency'),
    ),
    validators={
        validate_short_description: [
            ('Algorithm', 'Description'),
            ('Problem', 'Description'),
            ('Software', 'Description'),
            ('Benchmark', 'Description'),
        ],
        validate_reference: [
            ('Software', 'Reference'),
            ('Benchmark', 'Reference'),
        ],
    },
    targets='MaRDMO.algorithm.constants.get_uri_prefix_map',
    fills={
        'AT': ('Problem',   '_fill_problem_batch'),
        'S':  ('Software',  '_fill_software_batch'),
        'B':  ('Benchmark', '_fill_benchmark_batch'),
    },
)
'''The algorithm catalog's declaration.'''
