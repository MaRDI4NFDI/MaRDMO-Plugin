'''Dataclasses and fetch helpers that represent entities in the Model catalog.

Each class maps to one entity type collected from MaRDI Portal and Wikidata during
model documentation. Instances are populated from SPARQL query results and
carry the fields needed to render questionnaire answers and export entries.

Provides:

- :class:`ResearchField`             — mathematical research field
- :class:`ResearchProblem`           — research problem addressed by a model
- :class:`MathematicalModel`         — central model entity with all related data
- :class:`QuantityOrQuantityKind`    — scalar quantity or quantity kind used in a model
- :class:`MathematicalFormulation`   — formula / equation belonging to a model
- :class:`Task`                      — computational task derived from a model
- ``fetch_formula_data``             — batch-fetch formula LaTeX and quantity info
'''
# pylint: disable=too-many-lines

import logging

from dataclasses import dataclass, field
from typing import Optional

from .constants import data_properties_per_class, qudt_reference_ids

from ..core.config import get_items, get_options, get_properties, get_url
from ..core.properties import get_mathmoddb
from ..core.values import split_value
from ..core.models import QueryBatch, Relatant, RelatantWithClass, RelatantWithQualifier
from ..sources.wikibase import get_entities

logger = logging.getLogger(__name__)


def _extract_qualifier_qid(claim, pid_sym_rep):
    '''Return the QID of the symbol-represents qualifier on a claim, or None.

    Args:
        claim:       A single claim dict from a Wikibase ``wbgetentities`` response.
        pid_sym_rep: Property ID string for the "symbol represents" qualifier.

    Returns:
        QID string if the qualifier is present and carries an entity value,
        otherwise ``None``.
    '''
    for q_claim in claim.get('qualifiers', {}).get(pid_sym_rep, []):
        val = q_claim.get('datavalue', {}).get('value', {})
        if isinstance(val, dict):
            return val.get('id')
    return None


def _parse_formula_claims(entities, pid_formula, pid_in_formula, pid_sym_rep):
    '''Parse wbgetentities claims into intermediate formula data.

    Returns (intermediate, qty_qids_needed) where:
      intermediate = {qid: {'formulas': [...], 'raw_qty': [(symbol, qty_qid|None)]}}
      qty_qids_needed = set of QIDs whose labels/descriptions must be resolved
    '''
    intermediate    = {}
    qty_qids_needed = set()
    for qid, entity in entities.items():
        claims   = entity.get('claims', {})
        formulas = [
            c['mainsnak']['datavalue']['value']
            for c in claims.get(pid_formula, [])
            if c.get('mainsnak', {}).get('datavalue', {}).get('value')
        ]
        raw_qty = []
        for claim in claims.get(pid_in_formula, []):
            symbol  = claim.get('mainsnak', {}).get('datavalue', {}).get('value', '')
            qty_qid = _extract_qualifier_qid(claim, pid_sym_rep)
            if qty_qid:
                qty_qids_needed.add(qty_qid)
            raw_qty.append((symbol, qty_qid))
        intermediate[qid] = {'formulas': formulas, 'raw_qty': raw_qty}
    return intermediate, qty_qids_needed


def _fetch_qty_labels(api_url, qty_qids_needed):
    '''Fetch English labels/descriptions for a set of QIDs.

    Returns {qid: (label, description)}.
    '''
    if not qty_qids_needed:
        return {}
    entities = get_entities(api_url, qty_qids_needed, 'labels|descriptions', languages='en', resilient=True)
    return {
        qid: (
            entity.get('labels', {}).get('en', {}).get('value', 'No Label Provided!'),
            entity.get('descriptions', {}).get('en', {})
                  .get('value', 'No Description Provided!'),
        )
        for qid, entity in entities.items()
    }


def _build_formula_entry(data, qty_info, source='mardi'):
    '''Build the formula result dict for a single item from parsed intermediate data.

    Args:
        data:     Intermediate dict for one QID with keys ``formulas`` (list of
                  formula strings) and ``raw_qty`` (list of ``(symbol, qty_qid)`` tuples).
        qty_info: Dict mapping quantity QIDs to ``(label, description)`` tuples,
                  as returned by :func:`_fetch_qty_labels`.
        source:   ID prefix for quantity relatants (``'mardi'`` or ``'wikidata'``).

    Returns:
        Dict with keys ``formulas`` (list[str]), ``symbols`` (list[str]),
        and ``contains_quantity`` (list[Relatant]).
    '''
    symbols           = []
    contains_quantity = []
    for symbol, qty_qid in data['raw_qty']:
        symbols.append(symbol)
        label, desc = qty_info.get(
            qty_qid, ('No Label Provided!', 'No Description Provided!')
        )
        contains_quantity.append(
            Relatant.from_triple(f'{source}:{qty_qid}' if qty_qid else '', label, desc)
        )
    return {
        'formulas':          data['formulas'],
        'symbols':           symbols,
        'contains_quantity': contains_quantity,
    }


def fetch_formula_data(qids: list) -> dict:
    '''Fetch defining formula and in-defining-formula data via the wbgetentities API.

    Args:
        qids: List of raw QIDs such as ``['Q123', 'Q456']`` (without ``mardi:`` prefix).

    Returns:
        Dict mapping each QID to a result dict with keys:
        ``formulas`` (list[str]), ``symbols`` (list[str]),
        and ``contains_quantity`` (list[Relatant]).
        Returns an empty dict if *qids* is empty.
    '''
    if not qids:
        return {}

    props          = get_properties()
    pid_formula    = props.get('defining formula')
    pid_in_formula = props.get('in defining formula')
    pid_sym_rep    = props.get('symbol represents')
    api_url        = get_url('mardi', 'api')

    entities                    = get_entities(api_url, qids, 'claims', resilient=True)
    intermediate, qty_qids_needed = _parse_formula_claims(
        entities, pid_formula, pid_in_formula, pid_sym_rep
    )
    qty_info = _fetch_qty_labels(api_url, qty_qids_needed)

    return {
        qid: _build_formula_entry(data, qty_info, source='mardi')
        for qid, data in intermediate.items()
    }


def fetch_formula_data_wikidata(qids: list) -> dict:
    '''Fetch defining formula and in-defining-formula data from Wikidata via wbgetentities API.

    Uses Wikidata PIDs P2534 (defining formula), P7235 (in defining formula),
    and P9758 (symbol represents).

    Args:
        qids: List of raw QIDs such as ``['Q123', 'Q456']`` (without ``wikidata:`` prefix).

    Returns:
        Dict mapping each QID to a result dict with keys:
        ``formulas`` (list[str]), ``symbols`` (list[str]),
        and ``contains_quantity`` (list[Relatant]).
        Returns an empty dict if *qids* is empty.
    '''
    if not qids:
        return {}

    api_url = get_url('wikidata', 'api')

    entities                      = get_entities(api_url, qids, 'claims', resilient=True)
    intermediate, qty_qids_needed = _parse_formula_claims(
        entities, 'P2534', 'P7235', 'P9758'
    )
    qty_info = _fetch_qty_labels(api_url, qty_qids_needed)

    return {
        qid: _build_formula_entry(data, qty_info, source='wikidata')
        for qid, data in intermediate.items()
    }


@dataclass
class ResearchField(QueryBatch):
    '''Data Class For Research Field Item'''
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'ResearchField':
        '''Parse one SPARQL result row into a ResearchField instance.'''

        research_field = {
            # Get Aliases
            'aliases': split_value(
                data = data,
                key = 'aliases'
            ),
            # Get Long Description(s)
            'description_long': split_value(
                data = data,
                key = 'description_long'
            ),
            # Get Specialized By Relation(s)
            'specialized_by': split_value(
                data = data,
                key = 'specialized_by',
                transform = Relatant.from_query
            ),
            # Get Specializes Relation(s)
            'specializes': split_value(
                data = data,
                key = 'specializes',
                transform = Relatant.from_query
            ),
            # Get Similar To Relation(s)
            'similar_to': split_value(
                data = data,
                key = 'similar_to',
                transform = Relatant.from_query
            ),
            # Get Publication(s)
            'publications': split_value(
                data = data,
                key = 'publication',
                transform = Relatant.from_query
            )
        }

        return cls(
            **research_field
        )


@dataclass
class ResearchProblem(QueryBatch):
    '''Data Class For Research Problem Item'''
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    contained_in_field: list[Relatant] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'ResearchProblem':
        '''Parse one SPARQL result row into a ResearchProblem instance.'''

        research_problem = {
            # Get Aliases
            'aliases': split_value(
                data = data,
                key = 'aliases'
            ),
            # Get Long Description(s)
            'description_long': split_value(
                data = data,
                key = 'description_long'
            ),
            # Get Field Relation(s)
            'contained_in_field': split_value(
                data = data,
                key = 'contained_in_field',
                transform = Relatant.from_query
            ),
            # Get Specialized By Relation(s)
            'specialized_by': split_value(
                data = data,
                key = 'specialized_by',
                transform = Relatant.from_query
            ),
            # Get Specializes Relation(s)
            'specializes': split_value(
                data = data,
                key = 'specializes',
                transform = Relatant.from_query
            ),
            # Get Similar To Relation(s)
            'similar_to': split_value(
                data = data,
                key = 'similar_to',
                transform = Relatant.from_query
            ),
            # Get Publication(s)
            'publications': split_value(
                data = data,
                key = 'publication',
                transform = Relatant.from_query
            )
        }

        return cls(
            **research_problem
        )


@dataclass  # pylint: disable=too-many-instance-attributes
class MathematicalModel(QueryBatch):
    '''Data Class For Mathematical Model Item'''
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    properties: dict[int, str] = field(default_factory=dict)
    models: list[Relatant] = field(default_factory=list)
    assumes: list[Relatant] = field(default_factory=list)
    contains_formulation: list[Relatant] = field(default_factory=list)
    contains_boundary_condition: list[Relatant] = field(default_factory=list)
    contains_constraint_condition: list[Relatant] = field(default_factory=list)
    contains_coupling_condition: list[Relatant] = field(default_factory=list)
    contains_definition: list[Relatant] = field(default_factory=list)
    contains_initial_condition: list[Relatant] = field(default_factory=list)
    contains_final_condition: list[Relatant] = field(default_factory=list)
    contains_analytical_solution: list[Relatant] = field(default_factory=list)
    contains_governing_equation: list[Relatant] = field(default_factory=list)
    contains_computational_domain: list[Relatant] = field(default_factory=list)
    contains_weak_formulation: list[Relatant] = field(default_factory=list)
    contains_strong_formulation: list[Relatant] = field(default_factory=list)
    used_by: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    approximates: list[Relatant] = field(default_factory=list)
    approximated_by: list[Relatant] = field(default_factory=list)
    contains_model: list[Relatant] = field(default_factory=list)
    contained_in_model: list[Relatant] = field(default_factory=list)
    discretized_by: list[Relatant] = field(default_factory=list)
    discretizes: list[Relatant] = field(default_factory=list)
    linearized_by: list[Relatant] = field(default_factory=list)
    linearizes: list[Relatant] = field(default_factory=list)
    has_weak_formulation: list[Relatant] = field(default_factory=list)
    is_weak_formulation_of: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'MathematicalModel':
        '''Parse one SPARQL result row into a MathematicalModel instance.'''

        mathmoddb = get_mathmoddb()
        items = get_items()

        mathematical_model = {
            # Get Aliases
            'aliases': split_value(
                data = data,
                key = 'aliases'
            ),
            # Get Long Description(s)
            'description_long': split_value(
                data = data,
                key = 'description_long'
            ),
            # Get Properties
            # One line per property of the item, without empty lines in between
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(
                    prop for prop in data_properties_per_class['model']
                    if data.get(prop, {}).get('value') == 'True'
                )
            },
            # Get Problem Relation(s)
            'models': split_value(
                data = data,
                key = 'models',
                transform = Relatant.from_query
            ),
            # Get Assumption Relation(s)
            'assumes': split_value(
                data = data,
                key = 'assumes',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Contains Formulation Relation(s)
            'contains_formulation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == ''
            ),
            # Get Contains Boundary Condition Relation(s)
            'contains_boundary_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["boundary condition"]}'
            ),
            # Get Contains Constraint Condition Relation(s)
            'contains_constraint_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["constraint"]}'
            ),
            # Get Contains Coupling Condition Relation(s)
            'contains_coupling_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["coupling condition"]}'
            ),
            # Get Contains Definition Relation(s)
            'contains_definition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["definition"]}'
            ),
            # Get Contains Initial Condition Relation(s)
            'contains_initial_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["initial condition"]}'
            ),
            # Get Contains Final Condition Relation(s)
            'contains_final_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["final condition"]}'
            ),
            # Get Contains Analytical Solution Relation(s)
            'contains_analytical_solution': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["analytical solution"]}'
            ),
            # Get Contains Governing Equation Relation(s)
            'contains_governing_equation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["governing equation"]}'
            ),
            # Get Contains Computational Domain Relation(s)
            'contains_computational_domain': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = (
                    lambda item: item.qualifier == f'mardi:{items["computational domain"]}'
                )
            ),
            # Get Contains Weak Formulation Relation(s)
            'contains_weak_formulation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["weak formulation"]}'
            ),
            # Get Contains Strong Formulation Relation(s)
            'contains_strong_formulation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["strong formulation"]}'
            ),
            # Get Task Relation(s)
            'used_by': split_value(
                data = data,
                key = 'used_by',
                transform = Relatant.from_query
            ),
            # Get Specialized By Relation(s)
            'specialized_by': split_value(
                data = data,
                key = 'specialized_by',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Specializes Relation(s)
            'specializes': split_value(
                data = data,
                key = 'specializes',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Approximated By Relation(s)
            'approximated_by': split_value(
                data = data,
                key = 'approximated_by',
                transform = Relatant.from_query
            ),
            # Get Approximates Relation(s)
            'approximates': split_value(
                data = data,
                key = 'approximates',
                transform = Relatant.from_query
            ),
            # Get Contained In Model Relation(s)
            'contained_in_model': split_value(
                data = data,
                key = 'contained_in_model',
                transform = Relatant.from_query
            ),
            # Get Contains Model Relation(s)
            'contains_model': split_value(
                data = data,
                key = 'contains_model',
                transform = Relatant.from_query
            ),
            # Get Discretized By Relation(s)
            'discretized_by': split_value(
                data = data,
                key = 'discretized_by',
                transform = Relatant.from_query
            ),
            # Get Discretizes Relation(s)
            'discretizes': split_value(
                data = data,
                key = 'discretizes',
                transform = Relatant.from_query
            ),
            # Get Linearized By Relation(s)
            'linearized_by': split_value(
                data = data,
                key = 'linearized_by',
                transform = Relatant.from_query
            ),
            # Get Linearizes Relation(s)
            'linearizes': split_value(
                data = data,
                key = 'linearizes',
                transform = Relatant.from_query
            ),
            # Get Has Weak Formulation Relation(s)
            'has_weak_formulation': split_value(
                data = data,
                key = 'has_weak_formulation',
                transform = Relatant.from_query
            ),
            # Get Is Weak Formulation Of Relation(s)
            'is_weak_formulation_of': split_value(
                data = data,
                key = 'is_weak_formulation_of',
                transform = Relatant.from_query
            ),
            # Get Similar To Relation(s)
            'similar_to': split_value(
                data = data,
                key = 'similar_to',
                transform = Relatant.from_query
            ),
            # Get Publication(s)
            'publications': split_value(
                data = data,
                key = 'publication',
                transform = Relatant.from_query
            )
        }

        return cls(
            **mathematical_model
        )


@dataclass  # pylint: disable=too-many-instance-attributes
class QuantityOrQuantityKind(QueryBatch):
    '''Data Class For Quantity [Kind] Item'''
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    reference: dict[int, list[str]] = field(default_factory=dict)
    qclass: Optional[str] = None
    properties: dict[int, str] = field(default_factory=dict)
    formulas: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    contains_quantity: list[Relatant] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    approximated_by: list[Relatant] = field(default_factory=list)
    approximates: list[Relatant] = field(default_factory=list)
    discretized_by: list[Relatant] = field(default_factory=list)
    discretizes: list[Relatant] = field(default_factory=list)
    linearized_by: list[Relatant] = field(default_factory=list)
    linearizes: list[Relatant] = field(default_factory=list)
    nondimensionalized_by: list[Relatant] = field(default_factory=list)
    nondimensionalizes: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'QuantityOrQuantityKind':
        '''Parse one SPARQL result row into a QuantityOrQuantityKind instance.'''

        mathmoddb = get_mathmoddb()
        options = get_options()

        quantity = {
            # Get Aliases
            'aliases': split_value(
                data = data,
                key = 'aliases'
            ),
            # Get Long Description(s)
            'description_long': split_value(
                data = data,
                key = 'description_long'
            ),
            # Get Reference
            'reference': {
                idx: [options[prop], data[prop]['value']]
                for idx, prop in enumerate(qudt_reference_ids)
                if data.get(prop, {}).get('value')
            },
            # Get Quantity or Quantity Kind Class
            'qclass': data.get('class', {}).get('value'),
            # Get Properties
            # One line per property of the item, without empty lines in between
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(
                    prop for prop in data_properties_per_class['quantity']
                    if data.get(prop, {}).get('value') == 'True'
                )
            },
            # Get Specialized By Relation(s)
            'specialized_by': split_value(
                data = data,
                key = 'specialized_by',
                transform = RelatantWithClass.from_query
            ),
            # Get Specializes Relation(s)
            'specializes': split_value(
                data = data,
                key = 'specializes',
                transform = RelatantWithClass.from_query
            ),
            # Get Approximated By Relation(s)
            'approximated_by': split_value(
                data = data,
                key = 'approximated_by',
                transform = RelatantWithClass.from_query
            ),
            # Get Approximates Relation(s)
            'approximates': split_value(
                data = data,
                key = 'approximates',
                transform = RelatantWithClass.from_query
            ),
            # Get Discretized By Relation(s)
            'discretized_by': split_value(
                data = data,
                key = 'discretized_by',
                transform = RelatantWithClass.from_query
            ),
            # Get Discretizes Relation(s)
            'discretizes': split_value(
                data = data,
                key = 'discretizes',
                transform = RelatantWithClass.from_query
            ),
            # Get Linearized By Relation(s)
            'linearized_by': split_value(
                data = data,
                key = 'linearized_by',
                transform = RelatantWithClass.from_query
            ),
            # Get Linearizes Relation(s)
            'linearizes': split_value(
                data = data,
                key = 'linearizes',
                transform = RelatantWithClass.from_query
            ),
            # Get Nondimesionalized By Relation(s)
            'nondimensionalized_by': split_value(
                data = data,
                key = 'nondimensionalized_by',
                transform = RelatantWithClass.from_query
            ),
            # Get Nondimensionalizes Relation(s)
            'nondimensionalizes': split_value(
                data = data,
                key = 'nondimensionalizes',
                transform = RelatantWithClass.from_query
            ),
            # Get Similar To Relation(s)
            'similar_to': split_value(
                data = data,
                key = 'similar_to',
                transform = RelatantWithClass.from_query
            ),
            # Get Publication(s)
            'publications': split_value(
                data = data,
                key = 'publication',
                transform = Relatant.from_query
            )
        }

        return cls(
            **quantity
        )


@dataclass  # pylint: disable=too-many-instance-attributes
class MathematicalFormulation(QueryBatch):
    '''Data Class For Formulation Item'''
    reference: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    properties: dict[int, str] = field(default_factory=dict)
    formulas: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    contains_quantity: list[Relatant] = field(default_factory=list)
    assumes: list[Relatant] = field(default_factory=list)
    contains_formulation: list[Relatant] = field(default_factory=list)
    contains_assumption: list[Relatant] = field(default_factory=list)
    contains_boundary_condition: list[Relatant] = field(default_factory=list)
    contains_final_condition: list[Relatant] = field(default_factory=list)
    contains_initial_condition: list[Relatant] = field(default_factory=list)
    contains_constraint_condition: list[Relatant] = field(default_factory=list)
    contains_coupling_condition: list[Relatant] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    discretized_by: list[Relatant] = field(default_factory=list)
    discretizes: list[Relatant] = field(default_factory=list)
    approximated_by: list[Relatant] = field(default_factory=list)
    approximates: list[Relatant] = field(default_factory=list)
    linearized_by: list[Relatant] = field(default_factory=list)
    linearizes: list[Relatant] = field(default_factory=list)
    nondimensionalized_by: list[Relatant] = field(default_factory=list)
    nondimensionalizes: list[Relatant] = field(default_factory=list)
    has_weak_formulation: list[Relatant] = field(default_factory=list)
    is_weak_formulation_of: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'MathematicalFormulation':
        '''Parse one SPARQL result row into a MathematicalFormulation instance.'''

        mathmoddb = get_mathmoddb()
        items = get_items()

        mathematical_formulation = {
            # Get Aliases
            'aliases': split_value(
                data = data,
                key = 'aliases'
            ),
            # Get Long Description(s)
            'description_long': split_value(
                data = data,
                key = 'description_long'
            ),
            # Get Properties
            # One line per property of the item, without empty lines in between
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(
                    prop for prop in data_properties_per_class['formulation']
                    if data.get(prop, {}).get('value') == 'True'
                )
            },
            # Get Reference
            'reference': data.get('reference', {}).get('value'),
            # Get Assumption Relation(s)
            'assumes': split_value(
                data = data,
                key = 'assumes',
                transform = Relatant.from_query
            ),
            # Get Contains Formulation Relation(s)
            'contains_formulation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == ''
            ),
            # Get Contains Boundary Condition Relation(s)
            'contains_boundary_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["boundary condition"]}'
            ),
            # Get Contains Constraint Condition Relation(s)
            'contains_constraint_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["constraint"]}'
            ),
            # Get Contains Coupling Condition Relation(s)
            'contains_coupling_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["coupling condition"]}'
            ),
            # Get Contains Initial Condition Relation(s)
            'contains_initial_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["initial condition"]}'
            ),
            # Get Contains Final Condition Relation(s)
            'contains_final_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["final condition"]}'
            ),
            # Get Specialized By Relation(s)
            'specialized_by': split_value(
                data = data,
                key = 'specialized_by',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Specializes Relation(s)
            'specializes': split_value(
                data = data,
                key = 'specializes',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Approximated By Relation(s)
            'approximated_by': split_value(
                data = data,
                key = 'approximated_by',
                transform = Relatant.from_query
            ),
            # Get Approximates Relation(s)
            'approximates': split_value(
                data = data,
                key = 'approximates',
                transform = Relatant.from_query
            ),
            # Get Discretized By Relation(s)
            'discretized_by': split_value(
                data = data,
                key = 'discretized_by',
                transform = Relatant.from_query
            ),
            # Get Discretizes Relation(s)
            'discretizes': split_value(
                data = data,
                key = 'discretizes',
                transform = Relatant.from_query
            ),
            # Get Linearized By Relation(s)
            'linearized_by': split_value(
                data = data,
                key = 'linearized_by',
                transform = Relatant.from_query
            ),
            # Get Linearizes Relation(s)
            'linearizes': split_value(
                data = data,
                key = 'linearizes',
                transform = Relatant.from_query
            ),
            # Get Nondimensionalized By Relation(s)
            'nondimensionalized_by': split_value(
                data = data,
                key = 'nondimensionalized_by',
                transform = Relatant.from_query
            ),
            # Get Nondimesionalizes Relation(s)
            'nondimensionalizes': split_value(
                data = data,
                key = 'nondimensionalizes',
                transform = Relatant.from_query
            ),
            # Get Has Weak Formulation Relation(s)
            'has_weak_formulation': split_value(
                data = data,
                key = 'has_weak_formulation',
                transform = Relatant.from_query
            ),
            # Get Is Weak Formulation Of Relation(s)
            'is_weak_formulation_of': split_value(
                data = data,
                key = 'is_weak_formulation_of',
                transform = Relatant.from_query
            ),
            # Get Similar To Relation(s)
            'similar_to': split_value(
                data = data,
                key = 'similar_to',
                transform = Relatant.from_query
            ),
            # Get Publication(s)
            'publications': split_value(
                data = data,
                key = 'publication',
                transform = Relatant.from_query
            )
        }

        return cls(
            **mathematical_formulation
        )


@dataclass  # pylint: disable=too-many-instance-attributes
class Task(QueryBatch):
    '''Data Class For Task Item'''
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    properties: dict[int, str] = field(default_factory=dict)
    assumes: list[Relatant] = field(default_factory=list)
    contains_formulation: list[Relatant] = field(default_factory=list)
    contains_boundary_condition: list[Relatant] = field(default_factory=list)
    contains_final_condition: list[Relatant] = field(default_factory=list)
    contains_initial_condition: list[Relatant] = field(default_factory=list)
    contains_constraint_condition: list[Relatant] = field(default_factory=list)
    contains_coupling_condition: list[Relatant] = field(default_factory=list)
    contains_definition: list[Relatant] = field(default_factory=list)
    contains_analytical_solution: list[Relatant] = field(default_factory=list)
    contains_governing_equation: list[Relatant] = field(default_factory=list)
    contains_computational_domain: list[Relatant] = field(default_factory=list)
    contains_weak_formulation: list[Relatant] = field(default_factory=list)
    contains_strong_formulation: list[Relatant] = field(default_factory=list)
    contains_input: list[Relatant] = field(default_factory=list)
    contains_output: list[Relatant] = field(default_factory=list)
    contains_objective: list[Relatant] = field(default_factory=list)
    contains_parameter: list[Relatant] = field(default_factory=list)
    contains_constant: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    approximates: list[Relatant] = field(default_factory=list)
    approximated_by: list[Relatant] = field(default_factory=list)
    contains_task: list[Relatant] = field(default_factory=list)
    contained_in_task: list[Relatant] = field(default_factory=list)
    discretized_by: list[Relatant] = field(default_factory=list)
    discretizes: list[Relatant] = field(default_factory=list)
    linearized_by: list[Relatant] = field(default_factory=list)
    linearizes: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_single(cls, data: dict) -> 'Task':
        '''Parse one SPARQL result row into a Task instance.'''

        mathmoddb = get_mathmoddb()
        items = get_items()

        task = {
            # Get Aliases
            'aliases': split_value(
                data = data,
                key = 'aliases'
            ),
            # Get Long Description(s)
            'description_long': split_value(
                data = data,
                key = 'description_long'
            ),
            # Get Properties
            # One line per property of the item, without empty lines in between
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(
                    prop for prop in data_properties_per_class['task']
                    if data.get(prop, {}).get('value') == 'True'
                )
            },
            # Get Assumption Relation(s)
            'assumes': split_value(
                data = data,
                key = 'assumes',
                transform = Relatant.from_query
            ),
            # Get Contains Formulation Relation(s)
            'contains_formulation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == ''
            ),
            # Get Contains Boundary Condition Relation(s)
            'contains_boundary_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["boundary condition"]}'
            ),
            # Get Contains Constraint Condition Relation(s)
            'contains_constraint_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["constraint"]}'
            ),
            # Get Contains Coupling Condition Relation(s)
            'contains_coupling_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["coupling condition"]}'
            ),
            # Get Contains Definition Relation(s)
            'contains_definition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["definition"]}'
            ),
            # Get Contains Initial Condition Relation(s)
            'contains_initial_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["initial condition"]}'
            ),
            # Get Contains Final Condition Relation(s)
            'contains_final_condition': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["final condition"]}'
            ),
            # Get Contains Analytical Solution Relation(s)
            'contains_analytical_solution': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["analytical solution"]}'
            ),
            # Get Contains Governing Equation Relation(s)
            'contains_governing_equation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["governing equation"]}'
            ),
            # Get Contains Computational Domain Relation(s)
            'contains_computational_domain': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = (
                    lambda item: item.qualifier == f'mardi:{items["computational domain"]}'
                )
            ),
            # Get Contains Weak Formulation Relation(s)
            'contains_weak_formulation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["weak formulation"]}'
            ),
            # Get Contains Strong Formulation Relation(s)
            'contains_strong_formulation': split_value(
                data = data,
                key = 'contains_formulation',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["strong formulation"]}'
            ),
            # Get Contains Input Relation(s)
            'contains_input': split_value(
                data = data,
                key = 'contains_quantity',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["input"]}'
            ),
            # Get Contains Output Relation(s)
            'contains_output': split_value(
                data = data,
                key = 'contains_quantity',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["output"]}'
            ),
            # Get Contains Objective Relation(s)
            'contains_objective': split_value(
                data = data,
                key = 'contains_quantity',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["objective function"]}'
            ),
            # Get Contains Parameter Relation(s)
            'contains_parameter': split_value(
                data = data,
                key = 'contains_quantity',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["parameter"]}'
            ),
            # Get Contains Constant Relation(s)
            'contains_constant': split_value(
                data = data,
                key = 'contains_quantity',
                transform = RelatantWithQualifier.from_query,
                object_role = lambda item: item.qualifier == f'mardi:{items["constant"]}'
            ),
            # Get Specialized By Relation(s)
            'specialized_by': split_value(
                data = data,
                key = 'specialized_by',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Specializes Relation(s)
            'specializes': split_value(
                data = data,
                key = 'specializes',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Approximated By Relation(s)
            'approximated_by': split_value(
                data = data,
                key = 'approximated_by',
                transform = Relatant.from_query
            ),
            # Get Approximates Relation(s)
            'approximates': split_value(
                data = data,
                key = 'approximates',
                transform = Relatant.from_query
            ),
            # Get Contained In Relation(s)
            'contained_in_task': split_value(
                data = data,
                key = 'contained_in_task',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Contains Relation(s)
            'contains_task': split_value(
                data = data,
                key = 'contains_task',
                transform = RelatantWithQualifier.from_query
            ),
            # Get Discretized By Relation(s)
            'discretized_by': split_value(
                data = data,
                key = 'discretized_by',
                transform = Relatant.from_query
            ),
            # Get Discretizes Relation(s)
            'discretizes': split_value(
                data = data,
                key = 'discretizes',
                transform = Relatant.from_query
            ),
            # Get Linearized By Relation(s)
            'linearized_by': split_value(
                data = data,
                key = 'linearized_by',
                transform = Relatant.from_query
            ),
            # Get Linearizes Relation(s)
            'linearizes': split_value(
                data = data,
                key = 'linearizes',
                transform = Relatant.from_query
            ),
            # Get Similar To Relation(s)
            'similar_to': split_value(
                data = data,
                key = 'similar_to',
                transform = Relatant.from_query
            ),
            # Get Publication(s)
            'publications': split_value(
                data = data,
                key = 'publication',
                transform = Relatant.from_query
            )
        }

        return cls(
            **task
            )
