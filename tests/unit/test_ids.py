'''IDs of the user's own items: one export item per name and description.'''
import pytest

from MaRDMO.helpers import collect_items_without_section, extract_parts, unique_items
from MaRDMO.ids import is_item_id, is_own_item, is_portal_item, item_key


def language(identifier):
    return {'ID': identifier, 'Name': 'Lang', 'Description': 'a language'}


def test_own_items_are_user_ids_and_not_found():
    assert is_own_item('user:1') and is_own_item('not found')
    assert not is_own_item('mardi:Q1') and not is_own_item('wikidata:Q1') and not is_own_item('')
    assert is_item_id('user:1') and is_item_id('mardi:Q1') and not is_item_id('not found')


def test_own_items_with_the_same_name_and_description_are_one_item():
    assert item_key('user:1', 'Lang', 'd') == item_key('user:2', 'Lang', 'd') == item_key('not found', 'Lang', 'd')
    assert item_key('user:1', 'Lang', 'd') != item_key('mardi:Q1', 'Lang', 'd')


def test_the_same_new_language_on_two_software_pages_is_one_item():
    data = {'software': {0: {'programminglanguage': {0: language('user:1')}},
                         1: {'programminglanguage': {0: language('user:2')}}}}
    assert list(collect_items_without_section(data, 'software', 'programminglanguage').values()) == [
        language('user:1')]


def test_own_items_with_the_same_name_are_one_export_item_with_all_their_ids():
    '''All IDs get the portal ID after the export (helpers.replace_ids).'''
    data = {'quantity': {0: language('user:1'), 1: {'relation': {0: language('user:1')}}},
            'software': {0: {'programminglanguage': {0: language('user:2')}}}}
    items, _ = unique_items(data)
    assert list(items.values()) == [{**language('user:1'), 'orcid': '', 'zbmath': '', 'issn': '',
                                     'user_ids': ['user:1', 'user:2']}]


def test_portal_items_are_mardi_and_wikidata_ids():
    assert is_portal_item('mardi:Q1') and is_portal_item('wikidata:Q1')
    assert not any(is_portal_item(identifier) for identifier in ('user:1', 'not found', '', None, 'mardi'))


@pytest.mark.parametrize('text, parts', [
    ('Euler method (numerical method) [mardi]', ('Euler method', 'numerical method', 'mardi')),
    ('reaction rate (rate of a reaction)', ('reaction rate', 'rate of a reaction', 'user')),
    ('reaction rate', ('reaction rate', '', '')),     # label of a new item
    ('not found', ('not found', '', '')),
])
def test_text_parts(text, parts):
    assert extract_parts(text) == parts
