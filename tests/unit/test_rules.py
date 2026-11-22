'''Where a questionnaire value goes in the answers (MaRDMO.rules, #138).

Every question of the catalogs' ``questions.json`` uses a flag combination
:func:`~MaRDMO.rules.route` handles.  The paths of real projects are covered
by the golden tests.
'''
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from MaRDMO.rules import ALLOWED, FLAGS, flags, route

PACKAGE = Path(__file__).resolve().parents[2] / 'MaRDMO'


def questions():
    '''``(file, config)`` of every question of the catalogs' ``questions.json``.'''
    found = []

    def walk(path, data):
        if isinstance(data, dict):
            if 'uri' in data and 'key1' in data:
                found.append((path.parent.parent.name, data))
            for inner in data.values():
                walk(path, inner)
    for path in sorted(PACKAGE.glob('*/data/questions.json')):
        walk(path, json.loads(path.read_text()))
    return found


VALUE = SimpleNamespace(text='Euler method (algorithm)', option_uri='https://example.org/option',
                        external_id='mardi:Q1', set_index=3, collection_index=5)


def config(*names, key3=None):
    return {**{name: name in names for name in FLAGS}, 'key1': 'section', 'key2': 'key', 'key3': key3, 'uri': 'u'}


def test_every_question_uses_a_handled_combination():
    unhandled = [(catalog, question['uri']) for catalog, question in questions() if flags(question) not in ALLOWED]
    assert questions() and not unhandled


@pytest.mark.parametrize('names, path', [
    ((), ['section', 'key']),
    (('set_index',), ['section', 3, 'key']),                                     # the page
    (('set_prefix',), ['section', 7, 'key']),
    (('set_prefix', 'set_index'), ['section', 7, 'key', 3]),                    # a block in the page
    (('set_index', 'collection_index'), ['section', 3, 'key', 5]),
    (('set_prefix', 'set_index', 'collection_index'), ['section', 7, 'key', 3, 5]),
])
def test_the_path(names, path):
    assert route(VALUE, 'text', config(*names), 7)[1] == path


def test_key3_ends_the_path():
    assert route(VALUE, 'text', config('set_prefix', 'set_index', key3='symbol'), 7)[1] == ['section', 7, 'key', 3,
                                                                                              'symbol']


@pytest.mark.parametrize('names, entry', [
    (('set_prefix',), 'Euler method (algorithm)'),
    (('set_prefix', 'option_text'), ['https://example.org/option', 'Euler method (algorithm)']),
    (('set_index', 'external_id'), 'mardi:Q1'),                                  # the ID question of a page
    (('set_prefix', 'set_index', 'external_id'), {'ID': 'mardi:Q1', 'Name': 'Euler method',
                                                  'Description': 'algorithm'}),
])
def test_the_entry(names, entry):
    assert route(VALUE, 'text', config(*names), 7)[0] == entry


def test_an_unhandled_combination_is_an_error():
    with pytest.raises(ValueError, match='no rule handles'):
        route(VALUE, 'text', config('external_id', 'option_text'), 7)
