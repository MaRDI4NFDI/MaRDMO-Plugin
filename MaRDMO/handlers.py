'''General cross-catalog relation handler for MaRDMO.

Provides :class:`Information`, whose :meth:`~Information.relation` method is
called whenever a relation value is saved to any MaRDMO questionnaire.  It
dispatches to the appropriate sub-handler (:mod:`~MaRDMO.model.handlers`,
:mod:`~MaRDMO.algorithm.handlers`, or :mod:`~MaRDMO.workflow.handlers`)
based on the active project catalog, then registers and hydrates the related
entity in the questionnaire section.
'''

from .adders import add_entities, add_new_entities
from .helpers import extract_parts
from .ids import is_item_id
from .models import Relatant

from .algorithm.constants import get_uri_prefix_map as get_uri_prefix_map_algorithm
from .model.constants import get_uri_prefix_map as get_uri_prefix_map_model
from .workflow.constants import get_uri_prefix_map as get_uri_prefix_map_workflow

# Lazy singletons – avoid circular imports and repeated instantiation.
# Using a mutable dict so no global statement is needed.
_INFO_CACHE: dict = {}


def _get_model_info():
    '''Return the singleton :class:`~MaRDMO.model.handlers.Information` instance.'''
    if 'model' not in _INFO_CACHE:
        from .model.handlers import Information as M  # pylint: disable=import-outside-toplevel
        _INFO_CACHE['model'] = M()
    return _INFO_CACHE['model']


def _get_algo_info():
    '''Return the singleton :class:`~MaRDMO.algorithm.handlers.Information` instance.'''
    if 'algo' not in _INFO_CACHE:
        from .algorithm.handlers import Information as A  # pylint: disable=import-outside-toplevel
        _INFO_CACHE['algo'] = A()
    return _INFO_CACHE['algo']


def _get_workflow_info():
    '''Return the singleton :class:`~MaRDMO.workflow.handlers.Information` instance.'''
    if 'workflow' not in _INFO_CACHE:
        from .workflow.handlers import Information as W  # pylint: disable=import-outside-toplevel
        _INFO_CACHE['workflow'] = W()
    return _INFO_CACHE['workflow']


# Map prefix → (item_type, batch_method_name) per catalog family.
_MODEL_PREFIX_TO_FILL = {
    'AD':  ('Research Field',          '_fill_field_batch'),
    'RP':  ('Research Problem',        '_fill_problem_batch'),
    'CT':  ('Task',                    '_fill_task_batch'),
    'F':   ('Mathematical Formulation','_fill_formulation_batch'),
    'QQK': ('Quantity',                '_fill_quantity_batch'),
}

_ALGO_PREFIX_TO_FILL = {
    'AT': ('Problem',   '_fill_problem_batch'),
    'S':  ('Software',  '_fill_software_batch'),
    'B':  ('Benchmark', '_fill_benchmark_batch'),
}

_WORKFLOW_PREFIX_TO_FILL = {
    'A':  ('Algorithm',    '_fill_algorithm_batch'),
    'DS': ('Data Set',     '_fill_data_set_batch'),
    'S':  ('Software',     '_fill_software_batch'),
    'HW': ('Hardware',     '_fill_hardware_batch'),
    'PS': ('Process Step', '_fill_process_step_batch'),
}

# Dispatch table: catalog suffix → (get_uri_prefix_map_fn, prefix_map, get_info_fn)
# All catalogs accept both 'mardi' and 'wikidata' as hydration sources.
_CATALOG_DISPATCH = {
    'mardmo-model-catalog': (
        get_uri_prefix_map_model,
        _MODEL_PREFIX_TO_FILL,
        _get_model_info
    ),
    'mardmo-model-basics-catalog': (
        get_uri_prefix_map_model,
        _MODEL_PREFIX_TO_FILL,
        _get_model_info
    ),
    'mardmo-interdisciplinary-workflow-catalog': (
        get_uri_prefix_map_workflow,
        _WORKFLOW_PREFIX_TO_FILL,
        _get_workflow_info
    ),
    'mardmo-algorithm-catalog': (
        get_uri_prefix_map_algorithm,
        _ALGO_PREFIX_TO_FILL,
        _get_algo_info
    ),
}


class Information:  # pylint: disable=too-few-public-methods
    '''Class containing functions, querying external sources for specific
       entities and integrating the related metadata into the questionnaire.'''

    def __init__(self):
        pass

    def relation(self, instance):
        '''Handle a saved relation value by registering and hydrating the entity.

        Dispatches on the project's catalog to the appropriate sub-handler, then,
        by the ID the relation holds:

        1. Adds the related entity to the correct questionnaire section: an
           item of the MaRDI Portal or Wikidata as found there, a new item of
           the user's own (``user:`` ID) with the label (and description)
           typed in the relation.
        2. Hydrates a portal or Wikidata entity via ``fill_entity`` on the
           appropriate :class:`~MaRDMO.handler_base.BaseInformation` subclass.

        Args:
            instance: RDMO Value instance carrying ``project``, ``text``,
                      ``external_id``, and ``attribute`` attributes.
        '''
        catalog_key = str(instance.project.catalog).rsplit('/', maxsplit=1)[-1]

        dispatch = _CATALOG_DISPATCH.get(catalog_key)
        if dispatch is None:
            return
        get_uri_prefix_map, prefix_map, get_info = dispatch

        if not instance.text or not is_item_id(instance.external_id):
            return

        source = instance.external_id.split(':', 1)[0]
        # A new item's text is its label as typed (#129)
        label, description, _ = (instance.text, '', '') if source == 'user' else extract_parts(instance.text)
        config = get_uri_prefix_map()[instance.attribute.uri]
        datas  = [Relatant.from_triple(instance.external_id, label, description)]

        # --- Step 1: add entity to questionnaire section ---
        if source in ('mardi', 'wikidata'):
            add_entities(
                project      = instance.project,
                question_set = config["question_set"],
                datas        = datas,
                prefix       = config["prefix"],
            )
        elif source == 'user':
            add_new_entities(
                project      = instance.project,
                question_set = config["question_set"],
                datas        = datas,
                prefix       = config["prefix"],
            )
            return  # user-defined entities have no external data to hydrate

        # --- Step 2: explicitly hydrate the entity ---
        # Only mardi/wikidata-sourced entities carry SPARQL-queryable metadata.
        if source not in ('mardi', 'wikidata'):
            return

        entry = prefix_map.get(config["prefix"])
        if not entry:
            return
        item_type, batch_method_name = entry

        info     = get_info()
        batch_fn = getattr(info, batch_method_name)

        info.fill_entity(
            project           = instance.project,
            text              = instance.text,
            external_id       = instance.external_id,
            question_id       = config["question_id"],
            item_type         = item_type,
            batch_fill_method = batch_fn,
            catalog           = catalog_key,
        )
