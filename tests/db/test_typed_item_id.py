'''A Wikidata ID typed into a dropdown, with recorded answers of Wikidata and QLever (``typed_item_id``, #170).'''
from MaRDMO.providers import MaRDMOProvider


def options(key, search):
    return MaRDMOProvider(key, key, 'MaRDMO.providers.MaRDMOProvider').get_options(None, search=search)


def test_matlab_is_offered_in_the_software_dropdown(portal):
    portal('typed_item_id')
    offered = options('Software', 'wikidata:Q169478')
    assert [option['id'] for option in offered] == ['wikidata:Q169478']
    assert offered[0]['text'].startswith('MATLAB (')


def test_mass_is_not_offered_there(portal):
    portal('typed_item_id')
    assert options('Software', 'Wikidata: q11423') == []
