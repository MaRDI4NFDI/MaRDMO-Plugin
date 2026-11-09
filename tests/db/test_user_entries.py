'''The project's own items in the dropdowns of related items (queries.query_user_entries).'''
import pytest

import MaRDMO.queries as queries
from MaRDMO.providers import MaRDMOProvider
from tests.db.conftest import answer, save


@pytest.fixture
def options(monkeypatch):
    '''The options of the provider *key* for *search*, with the portal and Wikidata answering nothing.'''
    monkeypatch.setattr(queries, 'query_sources', lambda **kwargs: [])

    def get(project, key, search):
        provider = MaRDMOProvider(key, key, 'MaRDMO.providers.MaRDMOProvider')
        return [option['text'] for option in provider.get_options(project, search=search)]
    return get


def quantity(index, label, qclass=None, external_id=None):
    '''The answers of a quantity page: user-defined, or selected from a source (*external_id*).'''
    if external_id:
        answers = [answer('quantity/id', f'{label} (d) [{external_id.split(":")[0]}]',
                          external_id=external_id, set_index=index)]
    else:
        answers = [answer('quantity/id', 'not found', external_id=f'user:{index}', set_index=index),
                   answer('quantity/name', label, set_prefix=str(index)),
                   answer('quantity/description', 'd', set_prefix=str(index))]
    if qclass:
        answers.append(answer('quantity/is-quantity-or-quantity-kind', option=f'mathmoddb/{qclass}',
                              set_index=index))
    return answers


@pytest.fixture
def quantities(project):
    model = project('mardmo-model-catalog')
    save(model, *quantity(0, 'alpha quantity', 'quantity'),
         *quantity(1, 'alpha kind', 'quantity-kind'),
         *quantity(2, 'alpha unclassified'),
         *quantity(3, 'alpha wikidata kind', 'quantity-kind', external_id='wikidata:Q3686031'),
         *quantity(4, 'beta quantity', 'quantity'))
    return model


def test_quantity_relations_offer_quantities_and_those_without_class(quantities, options):
    assert options(quantities, 'RelatedQuantityWithoutCreation', 'alpha') == [
        'alpha quantity (d)', 'alpha unclassified (d)']


def test_quantity_kind_relations_offer_quantity_kinds_and_those_without_class(quantities, options):
    assert options(quantities, 'RelatedQuantityKindWithoutCreation', 'alpha') == [
        'alpha kind (d)', 'alpha unclassified (d)', 'alpha wikidata kind (d) [wikidata]']


def test_quantity_elements_offer_every_class_and_creation(quantities, options):
    '''Formula elements may be quantities or kinds; Wikidata items come from the Wikidata search.'''
    assert options(quantities, 'RelatedQuantityOrQuantityKindWithCreation', 'alpha') == [
        'alpha', 'alpha quantity (d)', 'alpha kind (d)', 'alpha unclassified (d)']


def test_user_entry_without_name_and_description(project, options):
    model = project('mardmo-model-catalog')
    save(model, answer('quantity/id', 'not found', external_id='user:0', set_index=0))
    assert options(model, 'RelatedQuantityWithoutCreation', 'provided') == [
        'No Label Provided! (No Description Provided!)']
