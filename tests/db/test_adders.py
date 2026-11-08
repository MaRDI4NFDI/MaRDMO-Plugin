'''Data properties written into a page when an item is filled in (adders.add_properties).'''
from types import SimpleNamespace

from MaRDMO.adders import add_properties
from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_mathmoddb
from tests.db.conftest import answer, save

URI = f'{BASE_URI}domain/quantity/properties'


def url(key):
    return get_mathmoddb().get(key=key)['url']


def lines(project, set_prefix='0'):
    '''{collection index: property key} of the quantity page *set_prefix*.'''
    keys = {url(key): key for key in ('is_deterministic', 'is_stochastic', 'is_dimensionless',
                                      'is_dimensional', 'is_dynamic', 'is_static')}
    return {value.collection_index: keys[value.option.uri]
            for value in project.values.filter(attribute__uri=URI, set_prefix=set_prefix)}


def fill(project, *keys, set_prefix=0):
    add_properties(project, SimpleNamespace(properties={idx: [url(key)] for idx, key in enumerate(keys)}),
                   URI, set_prefix)


def test_properties_fill_the_lines_in_order(project):
    model = project('mardmo-model-catalog')
    fill(model, 'is_deterministic', 'is_dimensional')
    assert lines(model) == {0: 'is_deterministic', 1: 'is_dimensional'}


def test_present_properties_keep_their_line_and_new_ones_fill_free_lines(project):
    '''A property the user put in line 1 stays there; line 0 was empty.'''
    model = project('mardmo-model-catalog')
    save(model, answer('quantity/properties', option='mathmoddb/is-dynamic', set_prefix='0', collection_index=1))
    fill(model, 'is_deterministic', 'is_dynamic', 'is_dimensional')
    assert lines(model) == {0: 'is_deterministic', 1: 'is_dynamic', 2: 'is_dimensional'}


def test_filling_twice_writes_nothing_new(project):
    model = project('mardmo-model-catalog')
    fill(model, 'is_deterministic', 'is_dimensional')
    fill(model, 'is_deterministic', 'is_dimensional')
    assert lines(model) == {0: 'is_deterministic', 1: 'is_dimensional'}


def test_contradicting_properties_are_both_left_out(project):
    '''Which side is right cannot be told; the checks report the missing property.'''
    model = project('mardmo-model-catalog')
    fill(model, 'is_deterministic', 'is_stochastic', 'is_static')
    assert lines(model) == {0: 'is_static'}


def test_other_pages_are_not_touched(project):
    model = project('mardmo-model-catalog')
    fill(model, 'is_deterministic', set_prefix=0)
    fill(model, 'is_static', set_prefix=1)
    assert lines(model, '0') == {0: 'is_deterministic'}
    assert lines(model, '1') == {0: 'is_static'}
