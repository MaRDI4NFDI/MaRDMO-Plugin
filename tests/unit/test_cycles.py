'''New items that refer to each other in cycles (#164).

The export creates every new item with its statements, after the items they
refer to.  payload.GeneratePayload.order_items builds these dependencies
from the statements (values and qualifiers) and breaks every cycle: of each
cycle, the item with the fewest statements to the other items of the cycle
(ties: the lower key) gets them afterwards as single statements (RELATION
entries).  Here on hand-made cases and on random graphs of up to 1000 items,
always with the same checks (:func:`check`).
'''
import json
import random
import time
from collections import Counter

import pytest

from MaRDMO.helpers import cycle_groups, is_cyclic, topological_order
from MaRDMO.payload import GeneratePayload

URL = 'https://portal.example.org'
P = 'P1'                                        # any property


def key(number):
    return f'Item{number:010d}'


def qualifier(value):
    return {'property': {'id': 'P2', 'data_type': 'wikibase-item'}, 'value': {'type': 'value', 'content': value}}


def statement(value, *qualifiers, prop=P):
    return [prop, 'wikibase-item', value, list(qualifiers)]


def build(items, existing=()):
    '''A payload with the new items *items* ``{key: [statement, ...]}`` and the portal items *existing*.'''
    payload = GeneratePayload(url=URL, dependency={}, wikibase={'properties': {}})
    for item in existing:
        payload.state.dictionary[item] = {'id': f'Q{int(item[4:])}', 'label': item, 'statements': []}
    for item, statements in items.items():
        payload.state.dictionary[item] = {'id': '', 'label': item, 'description': 'new',
                                          'statements': json.loads(json.dumps(statements))}
    return payload


def references(statement_):
    return {value for value in [statement_[2], *(q['value']['content'] for q in statement_[3])]
            if isinstance(value, str) and value.startswith('Item')}


def postponed(payload):
    '''``[(subject, statement)]`` of the RELATION entries, in their order.'''
    found = []
    for name, entry in payload.state.dictionary.items():
        if name.startswith('RELATION'):
            st = entry['payload']['statement']
            found.append((entry['url'].split('/items/')[1].split('/')[0],
                          [st['property']['id'], st['property']['data_type'], st['value']['content'],
                           st.get('qualifiers', [])]))
    return found


def check(items, existing=()):
    '''Order *items* and check what the upload needs; returns the payload.

    - no cycle is left, and every item comes after the items its statements refer to;
    - every statement arrives exactly once: in its item, or afterwards (RELATION);
    - a statement comes afterwards only if it closed a cycle: its item and an item it
      refers to were in one cycle, or it refers to its own item;
    - without cycles, nothing comes afterwards.
    '''
    payload = build(items, existing)
    payload.order_items()
    dictionary, dependency = payload.state.dictionary, payload.dependency
    assert not is_cyclic(dependency)
    order = topological_order(dependency)
    assert sorted(order) == sorted(k for k in dictionary if k.startswith('Item'))
    position = {item: index for index, item in enumerate(order)}
    for item in items:
        for st in dictionary[item]['statements']:
            assert references(st) <= dependency[item]
            assert all(position[ref] < position[item] for ref in references(st))
    later = postponed(payload)
    arrived = Counter(json.dumps([item, st]) for item in items for st in dictionary[item]['statements'])
    arrived.update(json.dumps([item, st]) for item, st in later)
    assert arrived == Counter(json.dumps([item, st]) for item, sts in items.items() for st in sts)
    groups = {member: set(group) for group in cycle_groups(
        {item: set().union(*map(references, sts)) & set(items) for item, sts in items.items()}) for member in group}
    for item, st in later:
        assert item in references(st) or references(st) & groups.get(item, set())
    if not groups and not any(item in references(st) for item, sts in items.items() for st in sts):
        assert later == []
    return payload


# --- Cases ------------------------------------------------------------------------------------

def test_no_cycle_keeps_every_statement_in_its_item():
    payload = check({key(1): [statement(key(2))], key(2): [statement(key(3))], key(3): []})
    assert payload.dependency == {key(1): {key(2)}, key(2): {key(3)}, key(3): set()}


def test_two_items_that_need_each_other():
    '''1 refers twice to 2, 2 once to 1: 2 gets its statement afterwards.'''
    payload = check({key(1): [statement(key(2)), statement(key(2), prop='P3')], key(2): [statement(key(1))]})
    assert postponed(payload) == [(key(2), statement(key(1)))]
    assert topological_order(payload.dependency) == [key(2), key(1)]


def test_a_tie_goes_to_the_lower_key():
    payload = check({key(1): [statement(key(2))], key(2): [statement(key(1))]})
    assert postponed(payload) == [(key(1), statement(key(2)))]


def test_a_cycle_of_three():
    payload = check({key(1): [statement(key(2))], key(2): [statement(key(3))], key(3): [statement(key(1))]})
    assert postponed(payload) == [(key(1), statement(key(2)))]


def test_a_cycle_through_a_qualifier():
    '''A formula assumes a model that contains it: the assumption closes the cycle.

    Both have one statement in the cycle; the model (lower key) gets its "contains" afterwards.
    '''
    model, formula, other = key(1), key(2), key(3)
    payload = check({model: [statement(formula)], formula: [statement(other, qualifier(model))], other: []})
    assert postponed(payload) == [(model, statement(formula))]
    assert payload.dependency[formula] == {other, model}


def test_a_statement_about_its_own_item():
    '''A quantity whose defining formula has a symbol for the quantity itself.'''
    symbol = ['P4', 'math', 'Q', [qualifier(key(1))]]
    payload = check({key(1): [symbol, statement(key(2))], key(2): []})
    assert postponed(payload) == [(key(1), symbol)]
    assert payload.dependency[key(1)] == {key(2)}


def test_portal_items_take_no_part_in_cycles():
    payload = check({key(1): [statement(key(9)), statement(key(2))], key(2): [statement(key(9))]}, existing=[key(9)])
    assert postponed(payload) == []
    assert payload.dependency[key(1)] == {key(9), key(2)}


def test_two_cycles_and_one_that_is_left():
    '''Breaking the cycle 1-2-3 by 1 leaves the cycle 2-3 (a tie: 2); 4-5 apart.'''
    items = {key(1): [statement(key(2))], key(2): [statement(key(3)), statement(key(1)), statement(key(1), prop='P3')],
             key(3): [statement(key(2)), statement(key(1))], key(4): [statement(key(5))], key(5): [statement(key(4))]}
    payload = check(items)
    assert {item for item, _ in postponed(payload)} == {key(1), key(2), key(4)}


def test_the_relation_entries_carry_the_qualifiers():
    payload = check({key(1): [statement(key(2), qualifier(key(3)))], key(2): [statement(key(1))], key(3): []})
    entry = next(e for name, e in payload.state.dictionary.items() if name.startswith('RELATION'))
    assert entry['url'] == f'{URL}/w/rest.php/wikibase/v1/entities/items/{key(1)}/statements'
    assert entry['payload']['statement']['qualifiers'] == [qualifier(key(3))]


def test_the_order_of_the_items_does_not_matter():
    items = {key(n): [statement(key(n % 6 + 1)), statement(key((n + 2) % 6 + 1))] for n in range(1, 7)}
    one = postponed(check(items))
    other = postponed(check(dict(reversed(items.items()))))
    assert one == other and one


# --- Random graphs ----------------------------------------------------------------------------

def graph(seed, size, per_item, qualifiers=0.3, own=0.01, existing=0):
    '''Random new items: *per_item* statements each on average, some referring in qualifiers or to themselves.'''
    rng = random.Random(seed)
    portal = [key(100000 + n) for n in range(existing)]
    names = [key(n) for n in range(1, size + 1)]
    items = {}
    for name in names:
        statements = []
        for _ in range(rng.randint(0, 2 * per_item)):
            target = name if rng.random() < own else rng.choice(names + portal)
            if rng.random() < qualifiers:
                statements.append(statement(rng.choice(names + portal), qualifier(target)))
            else:
                statements.append(statement(target))
        items[name] = statements
    return items, portal


@pytest.mark.parametrize('seed', range(40))
def test_random_small_graphs(seed):
    items, portal = graph(seed, size=random.Random(seed).randint(2, 40), per_item=2, existing=5)
    check(items, portal)


@pytest.mark.parametrize('size,per_item,limit', [
    (100, 1, 1), (100, 5, 1), (300, 3, 2),      # a large documentation: a fraction of a second
    (1000, 2, 5), (1000, 10, 30)])              # far beyond: seconds (its upload takes hours)
def test_large_graphs_in_time(size, per_item, limit):
    '''Up to 1000 items with 10000 references.

    The worst case is one giant cycle (1000 items, 10 references each): every
    break is followed by a new search for cycles in what is left (about 6 s
    here, the limits leave room for CI).
    '''
    items, portal = graph(size, size, per_item, existing=50)
    start = time.perf_counter()
    payload = build(items, portal)
    payload.order_items()
    elapsed = time.perf_counter() - start
    assert elapsed < limit, f'{elapsed:.2f} s'
    check(items, portal)


def test_one_long_cycle():
    '''A ring of 3000 items (no recursion limit): one statement waits.'''
    items = {key(n): [statement(key(n % 3000 + 1))] for n in range(1, 3001)}
    assert len(postponed(check(items))) == 1


def reachable(graph_, start):
    seen, todo = set(), [start]
    while todo:
        for nxt in graph_.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


@pytest.mark.parametrize('seed', range(30))
def test_cycle_groups_are_the_strongly_connected_components(seed):
    rng = random.Random(seed)
    nodes = [str(n) for n in range(rng.randint(1, 30))]
    graph_ = {node: {rng.choice(nodes) for _ in range(rng.randint(0, 3))} for node in nodes}
    reach = {node: reachable(graph_, node) for node in nodes}
    expected = sorted({tuple(sorted(n for n in nodes if n == node or (n in reach[node] and node in reach[n])))
                       for node in nodes})
    assert cycle_groups(graph_) == [list(group) for group in expected if len(group) > 1]
