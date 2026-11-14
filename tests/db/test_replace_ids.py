'''IDs of new portal items written back into the project after an export (helpers.replace_ids).'''
import pytest

from MaRDMO.constants import BASE_URI
from MaRDMO.helpers import replace_ids
from tests.db.conftest import answer, save


def get(project, path, **fields):
    value = project.values.get(attribute__uri=f'{BASE_URI}domain/{path}', **fields)
    return value.external_id, value.text


@pytest.fixture
def exported(project):
    '''A model project after an export that created three items.'''
    model = project('mardmo-model-catalog')
    save(model,
         # quantity 0: user-defined, now a portal item
         answer('quantity/id', 'not found', external_id='user:alpha', set_index=0),
         answer('quantity/name', 'alpha', set_prefix='0'),
         answer('quantity/description', 'first quantity', set_prefix='0'),
         # quantity 1: from Wikidata, now a portal item; relations to quantities 0 and 2
         answer('quantity/id', 'concentration (amount per volume) [wikidata]',
                external_id='wikidata:Q3686031', set_index=1),
         answer('quantity/quantity-to-quantity/relatant', 'alpha (older description)',
                external_id='user:alpha', set_prefix='1', set_index=0),
         answer('quantity/quantity-to-quantity/relatant', 'beta (other quantity)',
                external_id='user:beta', set_prefix='1', set_index=1),
         # quantity 2: user-defined, not exported
         answer('quantity/id', 'not found', external_id='user:beta', set_index=2),
         answer('quantity/name', 'beta', set_prefix='2'),
         answer('quantity/description', 'other quantity', set_prefix='2'),
         # publication 0: entered twice as the same item (merged by the export)
         answer('publication/id', 'not found', external_id='user:paper', set_index=0),
         answer('publication/id', 'not found', external_id='user:paper-again', set_index=1))
    replace_ids(model, {
        'Item0000000001': {'label': 'alpha', 'description': 'first quantity', 'old_id': 'user', 'new_qid': 'Q1',
                           'user_ids': ['user:alpha']},
        'Item0000000002': {'label': 'concentration', 'description': 'amount per volume',
                           'old_id': 'wikidata:Q3686031', 'new_qid': 'Q2'},
        'Item0000000003': {'label': 'A paper', 'description': 'scientific article', 'old_id': 'user',
                           'new_qid': 'Q3', 'user_ids': ['user:paper', 'user:paper-again']},
    })
    return model


def test_user_defined_item_gets_its_portal_id(exported):
    assert get(exported, 'quantity/id', set_index=0) == ('mardi:Q1', 'alpha (first quantity)')


def test_relations_to_the_item_get_its_portal_id(exported):
    '''Found by the ID; the text becomes the item's.'''
    assert get(exported, 'quantity/quantity-to-quantity/relatant', set_prefix='1', set_index=0) == (
        'mardi:Q1', 'alpha (first quantity)')


def test_wikidata_item_gets_its_portal_id(exported):
    assert get(exported, 'quantity/id', set_index=1) == (
        'mardi:Q2', 'concentration (amount per volume)')


def test_every_id_of_a_merged_item_gets_its_portal_id(exported):
    assert get(exported, 'publication/id', set_index=0) == ('mardi:Q3', 'A paper (scientific article)')
    assert get(exported, 'publication/id', set_index=1) == ('mardi:Q3', 'A paper (scientific article)')


def test_items_not_exported_stay_user_defined(exported):
    assert get(exported, 'quantity/id', set_index=2) == ('user:beta', 'not found')
    assert get(exported, 'quantity/quantity-to-quantity/relatant', set_prefix='1', set_index=1) == (
        'user:beta', 'beta (other quantity)')
