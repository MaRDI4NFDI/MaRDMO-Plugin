'''The statements of the payload against those on the MaRDI Portal.

Which statements the portal has already (:func:`exists_in_claims`), which
only add qualifiers to one of them (:func:`merge_qualifiers`), and which
symbols stand for another quantity there (:func:`check_symbols`).  The
claims of the portal items are fetched by :func:`fetch_claims`.
'''
import json
import logging
import re

import requests
from django.utils.translation import gettext as _

from ..sources.http import check_waits
from ..sources.wikibase import ENTITIES_PER_REQUEST, get_entities
from .errors import DocumentationProblem, PortalUnavailable

_logger = logging.getLogger(__name__)

QID_RE = re.compile(r'^Q\d+$')

# Qualifiers that give a statement its meaning: the same subject, property and
# object with another (or no) value of these is a statement of its own.  All
# other qualifiers add information and are added to an existing statement.
MEANING_QUALIFIERS = ('object has role', 'symbol represents', 'platform')
# Item-valued properties MaRDMO writes with a meaning qualifier ("contains"
# and "described by source" with a role, "uses" with a platform).  The existence
# check also finds a portal statement with such a qualifier for one without,
# so found statements of these are checked again.  Formulas ("in defining
# formula") have their own check that compares the qualifiers.
MEANING_PROPERTIES = ('contains', 'described by source', 'uses')


def fetch_claims(qids, api_url, deadline, what, cache=None):
    '''Return ``{qid: claims}`` of portal items, fetched with wbgetentities in chunks of 50.

    Items in *cache* (``{qid: claims}``, extended) are not fetched again.

    Raises:
        PortalUnavailable: If the claims cannot be fetched; *what* names the
            checked statements in the message (e.g. ``'formulas'``).
    '''
    claims_by_item = cache if cache is not None else {}
    qids = [qid for qid in qids if qid not in claims_by_item]
    for i in range(0, len(qids), ENTITIES_PER_REQUEST):
        try:
            entities = get_entities(api_url, qids[i:i + ENTITIES_PER_REQUEST], 'claims',
                                    waits=check_waits(), deadline=deadline)
        except (requests.exceptions.RequestException, ValueError) as exc:
            _logger.warning("Claims check via API failed: %s", exc)
            raise PortalUnavailable({
                'statements': _('Could not check which statements already exist on the MaRDI Portal '
                                '(API not reachable). Nothing was exported; please try again later.'),
                'formulas': _('Could not check which formulas already exist on the MaRDI Portal '
                              '(API not reachable). Nothing was exported; please try again later.'),
            }[what]) from exc
        for qid, entity in entities.items():
            claims_by_item[qid] = entity.get('claims', {})
    return claims_by_item


def resolve_item_reference(dictionary, value):
    '''Replace an ``Item<n>`` placeholder of the payload *dictionary* by its QID.

    Returns the QID, *value* unchanged when it is not a placeholder, or
    ``''`` when the placeholder refers to an item that does not exist yet.
    '''
    if isinstance(value, str) and value in dictionary:
        return dictionary[value].get('id', '')
    return value


def meaning_qualifiers(properties):
    '''Property IDs (of *properties*, ``{name: PID}``) of the qualifiers that give a statement its meaning.'''
    return {properties[name] for name in MEANING_QUALIFIERS if name in properties}


def exists_in_claims(dictionary, entry, claims):
    '''``'true'`` if the portal item of the RELATION *entry* holds its statement, else ``'false'``.

    The statement is there if a claim of the item has the property, the
    value and every qualifier of *entry* (:func:`snak_matches`).  A claim
    with more qualifiers matches too; :func:`merge_qualifiers` decides
    afterwards on the qualifiers that give a statement its meaning.  A
    statement of a new item, or with a value or qualifier that is a new
    item, is new.

    Args:
        dictionary: The payload dictionary.
        entry:      RELATION entry of *dictionary*.
        claims:     ``{qid: claims}`` of the portal items (:func:`fetch_claims`).
    '''
    statement = entry['payload']['statement']
    subject = resolve_item_reference(dictionary, entry['url'].split('/')[-2])
    if not (isinstance(subject, str) and QID_RE.match(subject)):
        return 'false'
    value = resolve_item_reference(dictionary, statement['value']['content'])
    data_type = statement['property']['data_type']
    wanted = [(q['property']['id'], resolve_item_reference(dictionary, q['value']['content']),
               q['property']['data_type']) for q in statement.get('qualifiers', [])]
    if value == '' or any(q_value == '' for _, q_value, _ in wanted):
        return 'false'
    for claim in claims.get(subject, {}).get(statement['property']['id'], []):
        if not snak_matches(claim.get('mainsnak', {}), value, data_type):
            continue
        if all(any(snak_matches(snak, q_value, q_type) for snak in claim.get('qualifiers', {}).get(q_prop, []))
               for q_prop, q_value, q_type in wanted):
            return 'true'
    return 'false'


def snak_matches(snak, value, data_type):
    '''Whether a portal snak (main value or qualifier) holds *value* of *data_type*.

    *value* is a payload value with item placeholders already resolved;
    an unresolved placeholder (``''``, an item created in this export)
    never matches.
    '''
    if value == '' or 'datavalue' not in snak:
        return False
    api = snak['datavalue'].get('value')
    if data_type == 'wikibase-item':
        return isinstance(api, dict) and api.get('id') == value
    if data_type == 'monolingualtext':
        text, language = (value.get('text'), value.get('language', 'en')) \
            if isinstance(value, dict) else (value, 'en')
        return isinstance(api, dict) and api.get('text') == text and api.get('language') == language
    if data_type == 'quantity':
        if not (isinstance(api, dict) and isinstance(value, dict)):
            return False
        same_unit = str(api.get('unit', '1')).rsplit('/', 1)[-1] == \
            str(value.get('unit', '1')).rsplit('/', 1)[-1]
        return same_unit and str(api.get('amount', '')).lstrip('+') == \
            str(value.get('amount', '')).lstrip('+')
    if data_type == 'time':
        return isinstance(api, dict) and isinstance(value, dict) \
            and api.get('time') == value.get('time') \
            and api.get('precision') == value.get('precision', api.get('precision'))
    return api == value


def same_meaning(entry_meaning, claim_meaning, role):
    '''Whether a portal statement's meaning qualifiers give it the meaning of the entry.

    Both are sets of ``(property ID, value)``.  Roles (*role*, the "object
    has role" property) are contained: a portal statement "as initial
    value and parameter" is also the one "as parameter" (MaRDMO writes one
    role per statement and imports such a statement as a relation for
    each role the questionnaire offers).  No role matches no role only.
    The other meaning qualifiers (symbol represents, platform) must be
    the same.
    '''
    entry_roles = {q for q in entry_meaning if q[0] == role}
    claim_roles = {q for q in claim_meaning if q[0] == role}
    if entry_meaning - entry_roles != claim_meaning - claim_roles:
        return False
    return entry_roles == claim_roles or bool(entry_roles) and entry_roles <= claim_roles


def merge_qualifiers(dictionary, properties, fetch):
    '''Turn new statements that only add qualifiers into additions to the portal statement.

    For every RELATION entry not found on the portal: if its item already
    holds a statement with the same property, value and the same
    qualifiers that give it its meaning (role, symbol represents,
    platform; also when there is none; the entry's roles may be some of
    the statement's, see :func:`same_meaning`), the entry is marked ``'partial'``
    with that statement's ID and the qualifiers it lacks, so posting adds
    them to the statement instead of writing it a second time.  An entry
    whose qualifiers are all there already is marked ``'true'``.  Several
    entries adding to the same statement share it; a qualifier is planned
    only once.

    Entries the existence check found are checked again when their property
    can carry a meaning qualifier (see :data:`MEANING_PROPERTIES`): the
    portal statement it found may have one the entry lacks (a plain
    "contains" against "contains" with a role).  Without a statement of
    the same meaning they are new.

    Args:
        dictionary: The payload dictionary; its RELATION entries are marked.
        properties: ``{name: PID}`` of the portal.
        fetch:      ``fetch(qids)`` returns ``{qid: claims}`` of portal items.

    Raises:
        PortalUnavailable: If the claims of an existing item cannot be fetched.
    '''
    meaning = meaning_qualifiers(properties)
    role = properties.get('object has role')
    # Properties whose statements can carry a meaning qualifier: a statement
    # found by the existence check may have one the payload statement lacks
    # (e.g. "contains" with a role for a plain "contains"), also when no
    # statement of this export has one
    with_meaning = {properties[name] for name in MEANING_PROPERTIES if name in properties} | {
        statement[0] for entry in dictionary.values()
        for statement in entry.get('statements') or []
        if len(statement) > 3 and any(q['property']['id'] in meaning for q in statement[3])
    } | {
        entry['payload']['statement']['property']['id']
        for key, entry in dictionary.items() if key.startswith('RELATION')
        and any(q['property']['id'] in meaning for q in entry['payload']['statement'].get('qualifiers', []))
    }
    candidates = []
    for key, entry in dictionary.items():
        if not key.startswith('RELATION'):
            continue
        statement = entry['payload']['statement']
        if entry.get('exists') == 'true' and statement['property']['id'] not in with_meaning:
            continue
        subject = resolve_item_reference(dictionary, entry['url'].split('/')[-2])
        value = resolve_item_reference(dictionary, statement['value']['content'])
        if not (isinstance(subject, str) and QID_RE.match(subject)) or value == '':
            continue        # new item: the statement cannot exist yet
        qualifiers = statement.get('qualifiers', [])
        meaning_values = {
            (q['property']['id'], json.dumps(resolve_item_reference(dictionary, q['value']['content']),
                                             sort_keys=True))
            for q in qualifiers if q['property']['id'] in meaning
        }
        added = [q for q in qualifiers if q['property']['id'] not in meaning]
        if any(v == '""' for _, v in meaning_values):
            continue        # its meaning refers to a new item: a new statement
        if not added and entry.get('exists') != 'true':
            continue        # nothing to add: a new statement
        candidates.append((key, subject, statement, value, meaning_values, added))
    if not candidates:
        return

    claims_by_item = fetch(sorted({c[1] for c in candidates}))
    planned = {}    # statement ID -> qualifiers already planned for it
    for key, subject, statement, value, meaning_values, added in candidates:
        prop_id, data_type = statement['property']['id'], statement['property']['data_type']
        best = None
        for claim in claims_by_item.get(subject, {}).get(prop_id, []):
            if not snak_matches(claim.get('mainsnak', {}), value, data_type):
                continue
            claim_meaning = {
                (q_prop, json.dumps(snak['datavalue']['value'].get('id')
                                    if isinstance(snak['datavalue']['value'], dict)
                                    and 'id' in snak['datavalue']['value']
                                    else snak['datavalue']['value'], sort_keys=True))
                for q_prop, snaks in claim.get('qualifiers', {}).items() if q_prop in meaning
                for snak in snaks if 'datavalue' in snak
            }
            if not same_meaning(meaning_values, claim_meaning, role):
                continue
            missing = [
                q for q in added
                if not any(snak_matches(snak, resolve_item_reference(dictionary, q['value']['content']),
                                              q['property']['data_type'])
                           for snak in claim.get('qualifiers', {}).get(q['property']['id'], []))
                and json.dumps(q, sort_keys=True) not in planned.get(claim['id'], set())
            ]
            # Fewest qualifiers to add; of those, a statement with exactly these roles
            rank = (len(missing), claim_meaning != meaning_values)
            if best is None or rank < best[2]:
                best = (claim['id'], missing, rank)
        entry = dictionary[key]
        if best is None:
            # no statement with this meaning on the portal: a new one (also
            # when the existence check found one with another meaning)
            entry['exists'] = 'false'
            continue
        if not best[1]:
            entry['exists'] = 'true'
            continue
        entry['exists'] = 'partial'
        entry['statement_id'] = best[0]
        entry['add_qualifiers'] = best[1]
        planned.setdefault(best[0], set()).update(json.dumps(q, sort_keys=True) for q in best[1])


def check_symbols(dictionary, properties, fetch):
    '''Compare new "in defining formula" statements with the symbols of the item on the portal.

    A symbol stands for exactly one quantity of its formula or quantity
    (the checks ensure this within the questionnaire).  For every such
    statement not on the portal yet, the statements of the same item
    with the same symbol decide:

    - one with another quantity: the export stops, MaRDMO cannot change
      what the symbol stands for (e.g. a symbol block of a fetched
      formula deleted and added again with another quantity);
    - one without a quantity (no "symbol represents"): it gets the
      quantity (``'partial'``) instead of a second statement;
    - none: a new statement.

    Args:
        dictionary: The payload dictionary; its RELATION entries are marked.
        properties: ``{name: PID}`` of the portal.
        fetch:      ``fetch(qids)`` returns ``{qid: claims}`` of portal items.

    Raises:
        DocumentationProblem: One argument per symbol that stands for another
            quantity on the portal.
        PortalUnavailable: If the claims cannot be fetched.
    '''
    in_formula, represents = properties.get('in defining formula'), properties.get('symbol represents')
    if not in_formula or not represents:
        return
    entries = []
    for key, entry in dictionary.items():
        if not key.startswith('RELATION') or entry.get('exists') != 'false':
            continue
        statement = entry['payload']['statement']
        if statement['property']['id'] != in_formula:
            continue
        subject = resolve_item_reference(dictionary, entry['url'].split('/')[-2])
        quantity = [q for q in statement.get('qualifiers', []) if q['property']['id'] == represents]
        if not (isinstance(subject, str) and QID_RE.match(subject)) or len(quantity) != 1:
            continue
        entries.append((key, subject, statement['value']['content'], quantity[0]))
    if not entries:
        return

    claims_by_item = fetch(sorted({e[1] for e in entries}))
    labels = {e.get('id'): e.get('label') for k, e in dictionary.items()
              if k.startswith('Item') and e.get('id')}
    conflicts, taken = [], set()
    for key, subject, symbol, qualifier in entries:
        quantity = resolve_item_reference(dictionary, qualifier['value']['content'])
        same_symbol = [
            (claim, {snak['datavalue']['value'].get('id')
                     for snak in claim.get('qualifiers', {}).get(represents, [])
                     if isinstance(snak.get('datavalue', {}).get('value'), dict)})
            for claim in claims_by_item.get(subject, {}).get(in_formula, [])
            if claim.get('mainsnak', {}).get('datavalue', {}).get('value') == symbol
        ]
        entry = dictionary[key]
        if quantity and any(quantity in found for _, found in same_symbol):
            entry['exists'] = 'true'
            continue
        other = sorted({qid for _, found in same_symbol for qid in found})
        if other:
            shown = ', '.join(f'{qid} ({labels[qid]})' if labels.get(qid) else qid for qid in other)
            conflicts.append(_(
                '"{label}" ({qid}): on the MaRDI Portal the symbol {symbol} already stands for {other}. '
                'MaRDMO cannot change this: use that quantity for the symbol, or correct it on the MaRDI Portal.'
            ).format(label=labels.get(subject) or subject, qid=subject, symbol=symbol, other=shown))
            continue
        incomplete = next((claim for claim, found in same_symbol
                           if not found and claim['id'] not in taken), None)
        if incomplete is not None:
            taken.add(incomplete['id'])
            entry['exists'] = 'partial'
            entry['statement_id'] = incomplete['id']
            entry['add_qualifiers'] = [qualifier]
    if conflicts:
        raise DocumentationProblem(*conflicts)
