'''Module containing Handlers for the Model Documentation.

Information inherits _entry, _collect_existing_ids, _hydrate_relatants,
and _fill from BaseInformation (MaRDMO/handler_base.py).

All SPARQL and write logic lives in the _fill_*_batch methods.
'''

import logging
from dataclasses import replace
from functools import partial

from rdmo.options.models import Option

from . import models
from .constants import props, relatant_uris, relation_uris

from ..handler_base import BaseInformation, _RelatantSpec, _fetch_by_source
from ..constants import BASE_URI
from ..getters import (
    get_mathmoddb,
    get_questions,
)
from ..helpers import value_editor
from ..adders import (
    add_basics,
    add_properties,
    add_references,
    add_relations_flexible,
    add_relations_static,
)

logger = logging.getLogger(__name__)


def _sparql_file(template, catalog):
    '''Return the basics or full variant of a SPARQL template path.
    Inserts -basics before the _<source>.sparql suffix, e.g.
    problem_mardi.sparql -> problem-basics_mardi.sparql.'''
    if 'basics' not in catalog:
        return template
    for suffix in ('_mardi.sparql', '_wikidata.sparql'):
        if template.endswith(suffix):
            return template[:-len(suffix)] + '-basics' + suffix
    return template


def write_defining_formula(project, page, data, set_index):
    """Write the formulas and the symbol table of a formula or quantity into its page.

    Args:
        project:   RDMO project instance.
        page:      Questions of the page (``questions["Mathematical Formulation"]``
                   or ``questions["Quantity"]``).
        data:      Item data with ``formulas``, ``symbols`` and ``contains_quantity``
                   (a quantity per symbol, ``id`` empty if the portal has none).
        set_index: Set index of the page.
    """
    for idx, formula in enumerate(data.formulas):
        value_editor(project=project, uri=f'{BASE_URI}{page["Formula"]["uri"]}',
                     info={'text': formula, 'collection_index': idx,
                           'set_index': 0, 'set_prefix': f'{set_index}|0'})

    for idx, symbol in enumerate(data.symbols):
        value_editor(project=project, uri=f'{BASE_URI}{page["Element Symbol"]["uri"]}',
                     info={'text': symbol, 'set_index': idx, 'set_prefix': f'{set_index}|0|0'})

    for idx, qty in enumerate(data.contains_quantity):
        if not qty.id:
            # A symbol without "symbol represents" on the portal: the quantity
            # stays empty, so the checks and the preview ask the user for it
            continue
        src_q = qty.id.split(':')[0]
        value_editor(project=project, uri=f'{BASE_URI}{page["Element Quantity"]["uri"]}',
                     info={'text': f'{qty.label} ({qty.description}) [{src_q}]',
                           'external_id': qty.id, 'set_index': idx, 'set_prefix': f'{set_index}|0|0'})


class Information(BaseInformation):
    '''Handlers for the Model Documentation questionnaire.'''

    _ENTITY_KEYS = (
        'Research Field', 'Research Problem', 'Quantity',
        'Mathematical Formulation', 'Task', 'Mathematical Model',
        'Publication',
    )

    def __init__(self):
        '''Load model and publication questions, MathModDB registry, and base URI.'''
        self.questions = get_questions('model') | get_questions('publication')
        self.mathmoddb = get_mathmoddb()
        self.base      = BASE_URI

    # ------------------------------------------------------------------ #
    #  Public signal-handler entry points                                  #
    # ------------------------------------------------------------------ #

    def field(self, instance):
        '''Handle Research Field ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Research Field', self._fill_field_batch)

    def problem(self, instance):
        '''Handle Research Problem ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Research Problem', self._fill_problem_batch)

    def quantity(self, instance):
        '''Handle Quantity ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Quantity', self._fill_quantity_batch)

    def formulation(self, instance):
        '''Handle Mathematical Formulation ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Mathematical Formulation', self._fill_formulation_batch)

    def task(self, instance):
        '''Handle Computational Task ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Task', self._fill_task_batch)

    def model(self, instance):
        '''Handle Mathematical Model ID save: hydrate basics and SPARQL data.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self._entry(instance, 'Mathematical Model', self._fill_model_batch)

    # ------------------------------------------------------------------ #
    #  Model-specific cascade helpers                                      #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    #  Batch _fill_* methods (one SPARQL query for N entities)            #
    # ------------------------------------------------------------------ #

    def _fill_field_batch(self, project, items, catalog, visited):
        '''Hydrate multiple Research Field pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix.
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return

        field      = self.questions['Research Field']
        data_by_id = _fetch_by_source(
            items,
            'model/queries/field_mardi.sparql',
            'model/queries/field_wikidata.sparql',
            models.ResearchField,
        )
        if not data_by_id:
            return

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Research Field', index=(0, set_index))

            for idx, alias in enumerate(data.aliases):
                value_editor(project=project, uri=f'{self.base}{field["Alias"]["uri"]}',
                             info={'text': alias, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            for idx, desc in enumerate(data.description_long):
                value_editor(project=project,
                             uri=f'{self.base}{field["Long Description"]["uri"]}',
                             info={'text': desc, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['Field'], 'mapping': self.mathmoddb},
                index={'set_prefix': set_index},
                statement={
                    'relation': f'{self.base}{field["IntraClassRelation"]["uri"]}',
                    'relatant': f'{self.base}{field["IntraClassElement"]["uri"]}',
                })

            self._hydrate_publications(project, data.publications,
                                       catalog, visited)

    def _fill_problem_batch(self, project, items, catalog, visited):
        '''Hydrate multiple Research Problem pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix.
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return

        problem    = self.questions['Research Problem']
        data_by_id = _fetch_by_source(
            items,
            _sparql_file('model/queries/problem_mardi.sparql', catalog),
            _sparql_file('model/queries/problem_wikidata.sparql', catalog),
            models.ResearchProblem,
        )
        if not data_by_id:
            return

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Research Problem', index=(0, set_index))

            for idx, alias in enumerate(data.aliases):
                value_editor(project=project, uri=f'{self.base}{problem["Alias"]["uri"]}',
                             info={'text': alias, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            for idx, desc in enumerate(data.description_long):
                value_editor(project=project,
                             uri=f'{self.base}{problem["Long Description"]["uri"]}',
                             info={'text': desc, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            add_relations_static(
                project=project, data=data,
                props={'keys': props['RP2RF']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{problem["RFRelatant"]["uri"]}'})

            self._hydrate_relatants(
                project=project, data=data, prop_keys=props['RP2RF'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Research Field"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Research Field"]["uri"]}',
                    prefix='AD',
                    fill_method=partial(self._fill, item_type='Research Field',
                                        batch_fill_method=self._fill_field_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_field_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['Problem'], 'mapping': self.mathmoddb},
                index={'set_prefix': set_index},
                statement={
                    'relation': f'{self.base}{problem["IntraClassRelation"]["uri"]}',
                    'relatant': f'{self.base}{problem["IntraClassElement"]["uri"]}',
                })

            self._hydrate_publications(project, data.publications,
                                       catalog, visited)

    def _fill_quantity_batch(self, project, items, catalog, visited):
        '''Hydrate multiple Quantity [Kind] pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix.
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return

        quantity   = self.questions['Quantity']
        data_by_id = _fetch_by_source(
            items,
            'model/queries/quantity_mardi.sparql',
            'model/queries/quantity_wikidata.sparql',
            models.QuantityOrQuantityKind,
        )
        if not data_by_id:
            return

        # Fetch formula data via API for mardi items
        mardi_qids = [eid.split(':')[-1] for _, eid, _ in items if eid.startswith('mardi:')]
        formula_data = models.fetch_formula_data(mardi_qids)
        for _, external_id, _ in items:
            if external_id.startswith('mardi:') and external_id in data_by_id:
                qid = external_id.split(':')[-1]
                if qid in formula_data:
                    fd = formula_data[qid]
                    data_by_id[external_id].formulas          = fd['formulas']
                    data_by_id[external_id].symbols           = fd['symbols']
                    data_by_id[external_id].contains_quantity = fd['contains_quantity']

        # Fetch formula data via API for wikidata items
        wikidata_qids = [eid.split(':')[-1] for _, eid, _ in items if eid.startswith('wikidata:')]
        wikidata_formula_data = models.fetch_formula_data_wikidata(wikidata_qids)
        for _, external_id, _ in items:
            if external_id.startswith('wikidata:') and external_id in data_by_id:
                qid = external_id.split(':')[-1]
                if qid in wikidata_formula_data:
                    fd = wikidata_formula_data[qid]
                    data_by_id[external_id].formulas          = fd['formulas']
                    data_by_id[external_id].symbols           = fd['symbols']
                    data_by_id[external_id].contains_quantity = fd['contains_quantity']

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Quantity', index=(0, set_index))

            for idx, alias in enumerate(data.aliases):
                value_editor(project=project, uri=f'{self.base}{quantity["Alias"]["uri"]}',
                             info={'text': alias, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            for idx, desc in enumerate(data.description_long):
                value_editor(project=project,
                             uri=f'{self.base}{quantity["Long Description"]["uri"]}',
                             info={'text': desc, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            if data.qclass:
                value_editor(project=project, uri=f'{self.base}{quantity["QorQK"]["uri"]}',
                             info={'option': Option.objects.get(
                                       uri=self.mathmoddb.get(key=data.qclass)['url']),
                                   'set_index': set_index})

            add_properties(project=project, data=data,
                           uri=f'{self.base}{quantity["Properties"]["uri"]}',
                           set_prefix=set_index)
            add_references(project=project, data=data,
                           uri=f'{self.base}{quantity["Reference"]["uri"]}',
                           set_prefix=set_index)

            write_defining_formula(project, quantity, data, set_index)

            # A quantity's defining formula references other quantities; give
            # each its own page, as _fill_formulation_batch does for formulae.
            self._hydrate_relatants(
                project=project, data=data, prop_keys=['contains_quantity'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Quantity"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Quantity"]["uri"]}',
                    prefix='QQK',
                    fill_method=partial(self._fill, item_type='Quantity',
                                        batch_fill_method=self._fill_quantity_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_quantity_batch,
                ))

            # The relation questions depend on the classes of the quantity and
            # of the relatant (Q→Q, Q→QK, QK→Q, QK→QK); one call per relatant
            # class, so relatants of the same relation share one set
            for (qclass, relatant_class), relation_key in relation_uris.items():
                if qclass != data.qclass:
                    continue
                add_relations_flexible(
                    project=project,
                    data=replace(data, **{
                        prop: [val for val in getattr(data, prop)
                               if val.item_class == relatant_class]
                        for prop in props['Quantity']
                    }),
                    props={'keys': props['Quantity'], 'mapping': self.mathmoddb},
                    index={'set_prefix': str(set_index)},
                    statement={
                        'relation': f'{self.base}{quantity[relation_key]["uri"]}',
                        'relatant': (f'{self.base}'
                                     f'{quantity[relatant_uris[(qclass, relatant_class)]]["uri"]}'),
                    })

            self._hydrate_publications(project, data.publications,
                                       catalog, visited)

    def _fill_formulation_batch(self, project, items, catalog, visited):
        '''Hydrate multiple Mathematical Formulation pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix.
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return

        formulation = self.questions['Mathematical Formulation']
        data_by_id  = _fetch_by_source(
            items,
            _sparql_file('model/queries/formulation_mardi.sparql', catalog),
            _sparql_file('model/queries/formulation_wikidata.sparql', catalog),
            models.MathematicalFormulation,
        )
        if not data_by_id:
            return

        # Fetch formula data via API for mardi items
        mardi_qids = [eid.split(':')[-1] for _, eid, _ in items if eid.startswith('mardi:')]
        formula_data = models.fetch_formula_data(mardi_qids)
        for _, external_id, _ in items:
            if external_id.startswith('mardi:') and external_id in data_by_id:
                qid = external_id.split(':')[-1]
                if qid in formula_data:
                    fd = formula_data[qid]
                    data_by_id[external_id].formulas          = fd['formulas']
                    data_by_id[external_id].symbols           = fd['symbols']
                    data_by_id[external_id].contains_quantity = fd['contains_quantity']

        # Fetch formula data via API for wikidata items
        wikidata_qids = [eid.split(':')[-1] for _, eid, _ in items if eid.startswith('wikidata:')]
        wikidata_formula_data = models.fetch_formula_data_wikidata(wikidata_qids)
        for _, external_id, _ in items:
            if external_id.startswith('wikidata:') and external_id in data_by_id:
                qid = external_id.split(':')[-1]
                if qid in wikidata_formula_data:
                    fd = wikidata_formula_data[qid]
                    data_by_id[external_id].formulas          = fd['formulas']
                    data_by_id[external_id].symbols           = fd['symbols']
                    data_by_id[external_id].contains_quantity = fd['contains_quantity']

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Mathematical Formulation', index=(0, set_index))

            for idx, alias in enumerate(data.aliases):
                value_editor(project=project,
                             uri=f'{self.base}{formulation["Alias"]["uri"]}',
                             info={'text': alias, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            for idx, desc in enumerate(data.description_long):
                value_editor(project=project,
                             uri=f'{self.base}{formulation["Long Description"]["uri"]}',
                             info={'text': desc, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            add_properties(project=project, data=data,
                           uri=f'{self.base}{formulation["Properties"]["uri"]}',
                           set_prefix=set_index)

            write_defining_formula(project, formulation, data, set_index)

            self._hydrate_relatants(
                project=project, data=data, prop_keys=['contains_quantity'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Quantity"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Quantity"]["uri"]}',
                    prefix='QQK',
                    fill_method=partial(self._fill, item_type='Quantity',
                                        batch_fill_method=self._fill_quantity_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_quantity_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['MF2MF'], 'mapping': self.mathmoddb},
                index={'set_prefix': f'{set_index}|0'},
                statement={
                    'relation': f'{self.base}{formulation["MF2MF"]["uri"]}',
                    'relatant': f'{self.base}{formulation["MFRelatant"]["uri"]}',
                })

            self._hydrate_relatants(
                project=project, data=data, prop_keys=props['MF2MF'],
                spec=_RelatantSpec(
                    question_id_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["ID"]["uri"]}'),
                    question_set_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["uri"]}'),
                    prefix='F',
                    fill_method=partial(self._fill, item_type='Mathematical Formulation',
                                        batch_fill_method=self._fill_formulation_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_formulation_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['Formulation'], 'mapping': self.mathmoddb},
                index={'set_prefix': set_index},
                statement={
                    'relation':   f'{self.base}{formulation["IntraClassRelation"]["uri"]}',
                    'relatant':   f'{self.base}{formulation["IntraClassElement"]["uri"]}',
                    'assumption': f'{self.base}{formulation["Assumption"]["uri"]}',
                })

            self._hydrate_qualifier_entities(
                project=project, data=data, prop_keys=props['Formulation'],
                spec=_RelatantSpec(
                    question_id_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["ID"]["uri"]}'),
                    question_set_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["uri"]}'),
                    prefix='F',
                    fill_method=partial(self._fill, item_type='Mathematical Formulation',
                                        batch_fill_method=self._fill_formulation_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_formulation_batch,
                ))
            self._hydrate_publications(project, data.publications,
                                       catalog, visited)

    def _fill_task_batch(self, project, items, catalog, visited):
        '''Hydrate multiple Computational Task pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix.
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return

        task       = self.questions['Task']
        data_by_id = _fetch_by_source(
            items,
            _sparql_file('model/queries/task_mardi.sparql', catalog),
            _sparql_file('model/queries/task_wikidata.sparql', catalog),
            models.Task,
        )
        if not data_by_id:
            return

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Task', index=(0, set_index))

            for idx, alias in enumerate(data.aliases):
                value_editor(project=project, uri=f'{self.base}{task["Alias"]["uri"]}',
                             info={'text': alias, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            for idx, desc in enumerate(data.description_long):
                value_editor(project=project,
                             uri=f'{self.base}{task["Long Description"]["uri"]}',
                             info={'text': desc, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            add_properties(project=project, data=data,
                           uri=f'{self.base}{task["Properties"]["uri"]}',
                           set_prefix=set_index)

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['T2MF'], 'mapping': self.mathmoddb},
                index={'set_prefix': f'{set_index}|0'},
                statement={
                    'relation': f'{self.base}{task["T2MF"]["uri"]}',
                    'relatant': f'{self.base}{task["MFRelatant"]["uri"]}',
                })

            self._hydrate_relatants(
                project=project, data=data, prop_keys=props['T2MF'],
                spec=_RelatantSpec(
                    question_id_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["ID"]["uri"]}'),
                    question_set_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["uri"]}'),
                    prefix='F',
                    fill_method=partial(self._fill, item_type='Mathematical Formulation',
                                        batch_fill_method=self._fill_formulation_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_formulation_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['T2Q'], 'mapping': self.mathmoddb},
                index={'set_prefix': f'{set_index}|0'},
                statement={
                    'relation': f'{self.base}{task["T2Q"]["uri"]}',
                    'relatant': f'{self.base}{task["QRelatant"]["uri"]}',
                })

            self._hydrate_relatants(
                project=project, data=data, prop_keys=props['T2Q'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Quantity"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Quantity"]["uri"]}',
                    prefix='QQK',
                    fill_method=partial(self._fill, item_type='Quantity',
                                        batch_fill_method=self._fill_quantity_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_quantity_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['Task'], 'mapping': self.mathmoddb},
                index={'set_prefix': set_index},
                statement={
                    'relation':   f'{self.base}{task["IntraClassRelation"]["uri"]}',
                    'relatant':   f'{self.base}{task["IntraClassElement"]["uri"]}',
                    'assumption': f'{self.base}{task["Assumption"]["uri"]}',
                })

            self._hydrate_qualifier_entities(
                project=project, data=data, prop_keys=props['Task'],
                spec=_RelatantSpec(
                    question_id_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["ID"]["uri"]}'),
                    question_set_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["uri"]}'),
                    prefix='F',
                    fill_method=partial(self._fill, item_type='Mathematical Formulation',
                                        batch_fill_method=self._fill_formulation_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_formulation_batch,
                ))
            self._hydrate_publications(project, data.publications,
                                       catalog, visited)

    def _fill_model_batch(self, project, items, catalog, visited):
        '''Hydrate multiple Mathematical Model pages with a single SPARQL query per source.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix.
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        if not items:
            return

        model_q    = self.questions['Mathematical Model']
        data_by_id = _fetch_by_source(
            items,
            _sparql_file('model/queries/model_mardi.sparql', catalog),
            _sparql_file('model/queries/model_wikidata.sparql', catalog),
            models.MathematicalModel,
        )
        if not data_by_id:
            return

        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Mathematical Model', index=(0, set_index))

            for idx, alias in enumerate(data.aliases):
                value_editor(project=project, uri=f'{self.base}{model_q["Alias"]["uri"]}',
                             info={'text': alias, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            for idx, desc in enumerate(data.description_long):
                value_editor(project=project,
                             uri=f'{self.base}{model_q["Long Description"]["uri"]}',
                             info={'text': desc, 'collection_index': idx,
                                   'set_index': 0, 'set_prefix': set_index})

            add_properties(project=project, data=data,
                           uri=f'{self.base}{model_q["Properties"]["uri"]}',
                           set_prefix=set_index)

            add_relations_static(
                project=project, data=data,
                props={'keys': props['MM2RP']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{model_q["RPRelatant"]["uri"]}'})

            self._hydrate_relatants(
                project=project, data=data, prop_keys=props['MM2RP'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Research Problem"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Research Problem"]["uri"]}',
                    prefix='RP',
                    fill_method=partial(self._fill, item_type='Research Problem',
                                        batch_fill_method=self._fill_problem_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_problem_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['MM2MF'], 'mapping': self.mathmoddb},
                index={'set_prefix': f'{set_index}|0'},
                statement={
                    'relation': f'{self.base}{model_q["MM2MF"]["uri"]}',
                    'relatant': f'{self.base}{model_q["MFRelatant"]["uri"]}',
                })

            self._hydrate_relatants(
                project=project, data=data, prop_keys=props['MM2MF'],
                spec=_RelatantSpec(
                    question_id_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["ID"]["uri"]}'),
                    question_set_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["uri"]}'),
                    prefix='F',
                    fill_method=partial(self._fill, item_type='Mathematical Formulation',
                                        batch_fill_method=self._fill_formulation_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_formulation_batch,
                ))

            add_relations_static(
                project=project, data=data,
                props={'keys': props['MM2T']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{model_q["TRelatant"]["uri"]}'})

            self._hydrate_relatants(
                project=project, data=data, prop_keys=props['MM2T'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Task"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Task"]["uri"]}',
                    prefix='CT',
                    fill_method=partial(self._fill, item_type='Task',
                                        batch_fill_method=self._fill_task_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_task_batch,
                ))

            add_relations_flexible(
                project=project, data=data,
                props={'keys': props['Model'], 'mapping': self.mathmoddb},
                index={'set_prefix': set_index},
                statement={
                    'relation':   f'{self.base}{model_q["IntraClassRelation"]["uri"]}',
                    'relatant':   f'{self.base}{model_q["IntraClassElement"]["uri"]}',
                    'assumption': f'{self.base}{model_q["Assumption"]["uri"]}',
                })

            self._hydrate_qualifier_entities(
                project=project, data=data, prop_keys=props['Model'],
                spec=_RelatantSpec(
                    question_id_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["ID"]["uri"]}'),
                    question_set_uri=(
                        f'{self.base}{self.questions["Mathematical Formulation"]["uri"]}'),
                    prefix='F',
                    fill_method=partial(self._fill, item_type='Mathematical Formulation',
                                        batch_fill_method=self._fill_formulation_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_formulation_batch,
                ))
            self._hydrate_publications(project, data.publications,
                                       catalog, visited)
