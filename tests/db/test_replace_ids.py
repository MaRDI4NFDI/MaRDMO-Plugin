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
         answer('quantity/id', 'not found', external_id='not found', set_index=0),
         answer('quantity/name', 'alpha', set_prefix='0'),
         answer('quantity/description', 'first quantity', set_prefix='0'),
         # quantity 1: from Wikidata, now a portal item; relations to quantities 0 and 2
         answer('quantity/id', 'concentration (amount per volume) [wikidata]',
                external_id='wikidata:Q3686031', set_index=1),
         answer('quantity/quantity-to-quantity/relatant', 'alpha (first quantity)',
                external_id='not found', set_prefix='1', set_index=0),
         answer('quantity/quantity-to-quantity/relatant', 'beta (other quantity)',
                external_id='not found', set_prefix='1', set_index=1),
         # quantity 2: user-defined, not exported
         answer('quantity/id', 'not found', external_id='not found', set_index=2),
         answer('quantity/name', 'beta', set_prefix='2'),
         answer('quantity/description', 'other quantity', set_prefix='2'),
         # publication 0: name and description on its own tab (set_prefix '')
         answer('publication/id', 'not found', external_id='not found', set_index=0),
         answer('publication/name', 'A paper', set_index=0),
         answer('publication/description', 'scientific article', set_index=0))
    replace_ids(model, {
        ('alpha', 'first quantity'): {'old_id': 'not found', 'new_qid': 'Q1'},
        ('concentration', 'amount per volume'): {'old_id': 'wikidata:Q3686031', 'new_qid': 'Q2'},
        ('A paper', 'scientific article'): {'old_id': 'not found', 'new_qid': 'Q3'},
    }, BASE_URI)
    return model


def test_user_defined_item_gets_its_portal_id(exported):
    assert get(exported, 'quantity/id', set_index=0) == ('mardi:Q1', 'alpha (first quantity) [mardi]')


def test_relations_to_the_item_get_its_portal_id(exported):
    assert get(exported, 'quantity/quantity-to-quantity/relatant', set_prefix='1', set_index=0) == (
        'mardi:Q1', 'alpha (first quantity) [mardi]')


def test_wikidata_item_gets_its_portal_id(exported):
    assert get(exported, 'quantity/id', set_index=1) == (
        'mardi:Q2', 'concentration (amount per volume) [mardi]')


def test_publication_gets_its_portal_id(exported):
    assert get(exported, 'publication/id', set_index=0) == ('mardi:Q3', 'A paper (scientific article) [mardi]')


def test_items_not_exported_stay_user_defined(exported):
    assert get(exported, 'quantity/id', set_index=2) == ('not found', 'not found')
    assert get(exported, 'quantity/quantity-to-quantity/relatant', set_prefix='1', set_index=1) == (
        'not found', 'beta (other quantity)')
