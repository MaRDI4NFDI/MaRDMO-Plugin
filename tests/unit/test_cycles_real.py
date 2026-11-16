'''The cycle breaking of the export on real relation graphs of the MaRDI Portal (#164).

tests/data/cycles/<list>-<QID>.json are models, algorithms and the workflow
of the portal with all their related items, every item made new (as if a
user documented all of it from scratch), reduced to what the ordering sees:
the statements that refer to other items.  Written by
dev-tests/cycles_real.py; here the checks of test_cycles run on them.
'''
import json
import time
from pathlib import Path

import pytest

from tests.unit.test_cycles import build, check

GRAPHS = sorted((Path(__file__).parents[1] / 'data' / 'cycles').glob('*.json'))


def items(path):
    '''The new items of the graph *path*, with statements as the export builds them.'''
    data = json.loads(path.read_text(encoding='utf-8'))
    return {key: [[prop, 'wikibase-item', value or 'Q1', [
        {'property': {'id': 'P0', 'data_type': 'wikibase-item'}, 'value': {'type': 'value', 'content': ref}}
        for ref in refs]] for prop, value, refs in statements] for key, statements in data['statements'].items()}


@pytest.mark.parametrize('path', GRAPHS, ids=[path.stem for path in GRAPHS])
def test_real_graph(path):
    graph = items(path)
    start = time.perf_counter()
    payload = build(graph)
    payload.order_items()
    assert time.perf_counter() - start < 2
    check(graph)
