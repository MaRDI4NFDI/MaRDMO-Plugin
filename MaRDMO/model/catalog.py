'''The model catalogs, as MaRDMO knows them: the full catalog and the basics (#198).'''
from ..catalogs import MODEL, Catalog, Registration
from ..constants import BASE_URI

CATALOG_MODEL_NAME = 'mardmo-model-catalog'
CATALOG_MODEL_BASICS_NAME = 'mardmo-model-basics-catalog'
CATALOG_MODEL = f'{BASE_URI}questions/{CATALOG_MODEL_NAME}'
CATALOG_MODEL_BASICS = f'{BASE_URI}questions/{CATALOG_MODEL_BASICS_NAME}'

REGISTRATION = Registration(
    catalogs=(
        Catalog(CATALOG_MODEL_NAME, MODEL, 'model', 'MaRDMO/preview_model.html',
                'MaRDMO.model.worker.PrepareModel', 'run_model'),
        Catalog(CATALOG_MODEL_BASICS_NAME, MODEL, 'model', 'MaRDMO/preview_model_basics.html',
                'MaRDMO.model.worker.PrepareModel', 'run_model', subset=True),
    ),
    questions={'model': 'model/data/questions.json'},
)
'''The model catalogs' declaration.'''
