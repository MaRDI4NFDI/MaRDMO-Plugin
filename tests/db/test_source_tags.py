'''The source of an option is shown in its help (a badge, #103, #142), not part of the text.'''
from types import SimpleNamespace

import pytest

import MaRDMO.components.dropdowns as dropdowns
from MaRDMO.components.fill.adders import add_entities
from MaRDMO.core.constants import BASE_URI
from MaRDMO.components.fill.adders import relation_exists
from MaRDMO.components.dropdowns import option_help
from MaRDMO.core.models import Relatant
from MaRDMO.providers import MaRDMOProvider
from tests.db.conftest import answer, save


def tag(identifier, text):
    '''The help of the option *identifier* with *text* (its layout, see tests/unit/test_option_help.py).'''
    return option_help(identifier, text)


MARDI = [{'id': 'mardi:Q1', 'text': 'alpha (first)'}]
WIKIDATA = [{'id': 'Q2', 'display': {'label': {'value': 'alpha'}, 'description': {'value': 'second'}}}]


@pytest.fixture
def portal(monkeypatch):
    '''The MaRDI Portal and Wikidata each find one "alpha"; returns what the searches gave.'''
    found = {'mardi': MARDI, 'wikidata': WIKIDATA}
    monkeypatch.setattr(dropdowns, '_cached_search', lambda source, *args: found[source])
    return found


def test_portal_and_wikidata_options_carry_their_source_in_the_help(portal):
    assert dropdowns.query_sources('alpha', 'Q1') == [
        {'id': 'not found', 'text': 'new item'},
        {'id': 'mardi:Q1', 'text': 'alpha (first)', 'help': tag('mardi:Q1', 'alpha (first)')},
        {'id': 'wikidata:Q2', 'text': 'alpha (second)', 'help': tag('wikidata:Q2', 'alpha (second)')}]


def test_the_cached_search_results_stay_as_they_are(portal):
    dropdowns.query_sources('alpha', 'Q1')
    assert MARDI == [{'id': 'mardi:Q1', 'text': 'alpha (first)'}]


@pytest.fixture
def model(project):
    '''A model project with an own quantity and a Wikidata quantity of the same name and description.'''
    documentation = project('mardmo-model-catalog')
    save(documentation,
         answer('quantity/id', 'new item', external_id='user:a', set_index=0),
         answer('quantity/name', 'alpha', set_prefix='0'),
         answer('quantity/description', 'second', set_prefix='0'),
         answer('quantity/id', 'alpha (second)', external_id='wikidata:Q2', set_index=1))
    return documentation


def options(project, key, search, monkeypatch):
    monkeypatch.setattr(dropdowns, 'query_sources', lambda **kwargs: [])
    return MaRDMOProvider(key, key, 'MaRDMO.providers.MaRDMOProvider').get_options(project, search=search)


def test_the_projects_items_are_offered_with_their_own_id_and_source(model, monkeypatch):
    '''The Wikidata item keeps its ID without a tag in its text; both items are offered.'''
    assert options(model, 'RelatedQuantityWithoutCreation', 'alpha', monkeypatch) == [
        {'id': 'user:a', 'text': 'alpha (second)', 'help': tag('user:a', 'alpha (second)')},
        {'id': 'wikidata:Q2', 'text': 'alpha (second)', 'help': tag('wikidata:Q2', 'alpha (second)')}]


def test_a_new_item_in_a_relation_is_tagged_new(model, monkeypatch):
    assert options(model, 'RelatedQuantityOrQuantityKindWithCreation', 'gamma', monkeypatch) == [
        {'id': 'not found', 'text': 'gamma', 'help': tag('not found', 'gamma')}]


def test_a_page_made_for_a_portal_item_has_no_tag(project):
    model = project('mardmo-model-catalog')
    add_entities(model, f'{BASE_URI}domain/quantity', [Relatant.from_triple('mardi:Q1', 'alpha', 'first')],
                 'QQK')
    assert model.values.get(attribute__uri=f'{BASE_URI}domain/quantity/id').text == 'alpha (first)'


def test_a_relation_is_the_same_by_its_id_only():
    '''An own item with the label and description of a portal item is another item.'''
    info = {'value_ids': ['user:a'], 'set_prefix_ids': [0]}
    portal_item = SimpleNamespace(id='mardi:Q1', label='alpha', description='first')
    assert not relation_exists(portal_item, 0, info)
    assert relation_exists(SimpleNamespace(id='user:a', label='', description=''), 0, info)
