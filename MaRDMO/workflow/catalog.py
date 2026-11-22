'''The interdisciplinary workflow catalog, as MaRDMO knows it (#198).'''
from ..catalogs import WORKFLOW, Catalog, Registration
from ..constants import BASE_URI

CATALOG_WORKFLOW_NAME = 'mardmo-interdisciplinary-workflow-catalog'
CATALOG_WORKFLOW = f'{BASE_URI}questions/{CATALOG_WORKFLOW_NAME}'

REGISTRATION = Registration(
    catalogs=(
        Catalog(CATALOG_WORKFLOW_NAME, WORKFLOW, 'workflow', 'MaRDMO/preview_workflow.html',
                'MaRDMO.workflow.worker.PrepareWorkflow', 'run_workflow'),
    ),
    questions={'workflow': 'workflow/data/questions.json'},
)
'''The workflow catalog's declaration.'''
