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
import random
import time

from dataclasses import dataclass, field
from typing import Optional

import requests

from .constants import data_properties_per_class, qudt_reference_ids

from ..getters import get_items, get_mathmoddb, get_options, get_properties, get_url
from ..helpers import split_value
from ..models import Relatant, RelatantWithClass, RelatantWithQualifier

logger = logging.getLogger(__name__)

_USER_AGENT = 'MaRDMO (https://zib.de; reidelbach@zib.de)'

# --- wbgetentities resilience knobs -----------------------------------------
# The MaRDI portal API is prone to transient failures under database load:
# HTTP 500/503 pages *and* HTTP 200 responses whose body is a MediaWiki
# ``{"error": ...}`` object (e.g. ``internal_api_error_DBConnectionError``).
_WB_CHUNK_SIZE   = 50     # QIDs per request
_WB_MAX_ATTEMPTS = 4      # attempts per (sub-)chunk before splitting / giving up
_WB_BACKOFF_BASE = 1.0    # seconds; delay is base * 2**(attempt-1) + jitter
_WB_MAX_BACKOFF  = 20.0   # cap on a single retry delay
_WB_TIMEOUT      = 30     # per-request timeout (seconds)
_WB_OUTAGE_TRIP  = 3      # consecutive dead chunks that open the circuit breaker
_WB_COOLDOWN     = 120    # seconds to stay "open" (fail fast) after tripping

# Process-wide circuit-breaker state, keyed by endpoint. While a breaker is
# open, calls to that endpoint return immediately with whatever is cached so a
# full portal outage degrades to "partial import" fast instead of retrying for
# minutes on every entity.
_wb_breakers: dict = {}


class _WbOutage(Exception):
    '''A wbgetentities failure that looks endpoint-wide (5xx / connection / DB error).'''


def _wbgetentities_batch(api_url, qids, props, extra_params=None):
    '''Fetch Wikibase entities via ``wbgetentities`` with retry and a circuit breaker.

    QIDs are requested in chunks of :data:`_WB_CHUNK_SIZE`. Each chunk is
    retried with exponential backoff on transient failures — HTTP 5xx, network
    errors, timeouts, and HTTP 200 bodies carrying a MediaWiki ``error``
    object. A chunk that keeps timing out is bisected to isolate a single
    unresponsive entity. Once :data:`_WB_OUTAGE_TRIP` chunks die in a row the
    endpoint's circuit breaker opens for :data:`_WB_COOLDOWN` seconds and
    further calls short-circuit, returning only what resolved.

    Args:
        api_url:     Base URL of the Wikibase API endpoint.
        qids:        List of QID strings to fetch (e.g. ``['Q123', 'Q456']``).
        props:       Pipe-separated property string passed to ``wbgetentities``
                     (e.g. ``'labels|descriptions'`` or ``'claims'``).
        extra_params: Optional dict of additional API parameters (e.g. ``{'languages': 'en'}``).

    Returns:
        Dict mapping QID strings to their entity data dicts. May be partial or
        empty if the endpoint is unavailable.
    '''
    params_base = {
        'action': 'wbgetentities',
        'props':  props,
        'format': 'json',
        **(extra_params or {}),
    }

    if _wb_circuit_open(api_url):
        logger.warning("wbgetentities: circuit open for %s, skipping %s qids",
                       api_url, len(qids))
        return {}

    result = {}
    for i in range(0, len(qids), _WB_CHUNK_SIZE):
        chunk = qids[i:i + _WB_CHUNK_SIZE]
        try:
            result.update(_wbget_chunk(api_url, params_base, chunk))
        except _WbOutage:
            _wb_record_failure(api_url)
            if _wb_circuit_open(api_url):
                logger.error("wbgetentities: %s unresponsive, aborting batch", api_url)
                break
        else:
            _wb_reset(api_url)

    return result


def _wb_circuit_open(api_url):
    '''True while *api_url*'s breaker is within its cooldown window.'''
    tripped_at = _wb_breakers.get(api_url, {}).get('open_until', 0)
    return time.monotonic() < tripped_at


def _wb_record_failure(api_url):
    '''Count one dead chunk; open the breaker once the streak hits the limit.'''
    breaker = _wb_breakers.setdefault(api_url, {'fails': 0, 'open_until': 0})
    breaker['fails'] += 1
    if breaker['fails'] >= _WB_OUTAGE_TRIP:
        breaker['open_until'] = time.monotonic() + _WB_COOLDOWN


def _wb_reset(api_url):
    '''Clear the failure streak for *api_url* after a successful chunk.'''
    if api_url in _wb_breakers:
        _wb_breakers[api_url] = {'fails': 0, 'open_until': 0}


def _wbget_chunk(api_url, params_base, chunk):
    '''Fetch one chunk of QIDs, retrying transient failures with backoff.

    Args:
        api_url:     Wikibase API endpoint.
        params_base: Shared query params (without ``ids``).
        chunk:       List of QID strings for this (sub-)request.

    Returns:
        Dict ``{qid: entity}`` for every QID that resolved (may be partial).

    Raises:
        _WbOutage: The chunk still fails after all retries with an
            endpoint-wide error. The caller feeds this to the circuit breaker.
    '''
    params = {**params_base, 'ids': '|'.join(chunk)}
    outage = None

    for attempt in range(1, _WB_MAX_ATTEMPTS + 1):
        retry_after = None
        try:
            resp = requests.get(
                api_url, params=params,
                headers={'User-Agent': _USER_AGENT}, timeout=_WB_TIMEOUT,
            )
            if resp.status_code >= 500:
                retry_after = resp.headers.get('Retry-After')
                raise _WbOutage(f'HTTP {resp.status_code}')
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, dict) and 'error' in body:
                raise _WbOutage(f"api-error:{body['error'].get('code', 'unknown')}")
            return body.get('entities', {})
        except requests.exceptions.Timeout:
            outage = None
        except (requests.exceptions.RequestException, _WbOutage, ValueError) as exc:
            outage = _WbOutage(str(exc))

        if attempt < _WB_MAX_ATTEMPTS:
            delay = min(_WB_BACKOFF_BASE * 2 ** (attempt - 1), _WB_MAX_BACKOFF)
            if retry_after and str(retry_after).isdigit():
                delay = max(delay, float(retry_after))
            delay += random.uniform(0, 0.5)
            time.sleep(delay)

    # Retries exhausted. A persistent timeout may be one oversized entity —
    # bisect to isolate it. An endpoint-wide error propagates to the breaker.
    if outage is None and len(chunk) > 1:
        mid = len(chunk) // 2
        return {
            **_wbget_chunk(api_url, params_base, chunk[:mid]),
            **_wbget_chunk(api_url, params_base, chunk[mid:]),
        }

    logger.error("wbgetentities failed for %s..%s", chunk[0], chunk[-1])
    if outage is not None:
        raise outage
    return {}


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
    entities = _wbgetentities_batch(
        api_url, list(qty_qids_needed), 'labels|descriptions',
        extra_params={'languages': 'en'},
    )
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

    entities                    = _wbgetentities_batch(api_url, qids, 'claims')
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

    entities                      = _wbgetentities_batch(api_url, qids, 'claims')
    intermediate, qty_qids_needed = _parse_formula_claims(
        entities, 'P2534', 'P7235', 'P9758'
    )
    qty_info = _fetch_qty_labels(api_url, qty_qids_needed)

    return {
        qid: _build_formula_entry(data, qty_info, source='wikidata')
        for qid, data in intermediate.items()
    }

@dataclass
class ResearchField:
    '''Data Class For Research Field Item'''
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query(cls, raw_data: dict) -> 'ResearchField':
        '''Generate Class Item From Query (single-item, backward-compatible).'''
        return cls.from_query_single(raw_data[0])

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, ResearchField]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

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
class ResearchProblem:
    '''Data Class For Research Problem Item'''
    aliases: list[str] = field(default_factory=list)
    description_long: list[str] = field(default_factory=list)
    contained_in_field: list[Relatant] = field(default_factory=list)
    specialized_by: list[Relatant] = field(default_factory=list)
    specializes: list[Relatant] = field(default_factory=list)
    similar_to: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query(cls, raw_data: dict) -> 'ResearchProblem':
        '''Generate Class Item From Query (single-item, backward-compatible).'''
        return cls.from_query_single(raw_data[0])

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, ResearchProblem]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

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
class MathematicalModel:
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
    def from_query(cls, raw_data: dict) -> 'MathematicalModel':
        '''Generate Class Item From Query (single-item, backward-compatible).'''
        return cls.from_query_single(raw_data[0])

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, MathematicalModel]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

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
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(data_properties_per_class['model'])
                if data.get(prop, {}).get('value') == 'True'
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
class QuantityOrQuantityKind:
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
    def from_query(cls, raw_data: dict) -> 'QuantityOrQuantityKind':
        '''Generate Class Item From Query (single-item, backward-compatible).'''
        return cls.from_query_single(raw_data[0])

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, QuantityOrQuantityKind]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

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
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(data_properties_per_class['quantity'])
                if data.get(prop, {}).get('value') == 'True'
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
class MathematicalFormulation:
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
    def from_query(cls, raw_data: dict) -> 'MathematicalFormulation':
        '''Generate Class Item From Query (single-item, backward-compatible).'''
        return cls.from_query_single(raw_data[0])

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, MathematicalFormulation]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

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
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(data_properties_per_class['formulation'])
                if data.get(prop, {}).get('value') == 'True'
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
class Task:
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
    def from_query(cls, raw_data: dict) -> 'Task':
        '''Generate Class Item From Query (single-item, backward-compatible).'''
        return cls.from_query_single(raw_data[0])

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, Task]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

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
            'properties': {
                idx: [mathmoddb.get(key=prop)["url"]]
                for idx, prop in enumerate(data_properties_per_class['task'])
                if data.get(prop, {}).get('value') == 'True'
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
