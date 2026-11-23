'''General cross-catalog relation handler for MaRDMO.

Provides :class:`Information`, whose :meth:`~Information.relation` method is
called whenever a relation value is saved to any MaRDMO questionnaire.  It
looks up the declaration of the project's catalog
(:class:`~MaRDMO.core.catalogs.Registration`: where the related items go, how
they are filled in, by which handler class), then registers and hydrates the
related entity in the questionnaire section.
'''

from .adders import add_entities, add_new_entities
from .core.catalogs import catalog_of, registration_of
from .core.values import extract_parts
from .core.ids import is_item_id
from .core.models import Relatant

# The handler of each catalog, one instance per handler class, created when
# first used (a mutable dict, so no global statement is needed)
_INFO_CACHE: dict = {}


def _information(registration):
    '''Return the handler (an instance of the class the *registration* names) of its catalog.'''
    if registration.information not in _INFO_CACHE:
        _INFO_CACHE[registration.information] = registration.information_class()
    return _INFO_CACHE[registration.information]


class Information:  # pylint: disable=too-few-public-methods
    '''Class containing functions, querying external sources for specific
       entities and integrating the related metadata into the questionnaire.'''

    def __init__(self):
        pass

    def relation(self, instance):
        '''Handle a saved relation value by registering and hydrating the entity.

        Looks up the declaration of the project's catalog, then,
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
        catalog = catalog_of(instance.project)
        registration = registration_of(catalog) if catalog else None
        if registration is None or not registration.fills:
            return

        if not instance.text or not is_item_id(instance.external_id):
            return

        source = instance.external_id.split(':', 1)[0]
        # A new item's text is its label as typed (#129)
        label, description, _ = (instance.text, '', '') if source == 'user' else extract_parts(instance.text)
        config = registration.relation_targets()[instance.attribute.uri]
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

        entry = registration.fills.get(config["prefix"])
        if not entry:
            return
        item_type, batch_method_name = entry

        info     = _information(registration)
        batch_fn = getattr(info, batch_method_name)

        info.fill_entity(
            project           = instance.project,
            text              = instance.text,
            external_id       = instance.external_id,
            question_id       = config["question_id"],
            item_type         = item_type,
            batch_fill_method = batch_fn,
            catalog           = catalog.name,
        )
