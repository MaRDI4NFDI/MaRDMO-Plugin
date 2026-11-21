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


# On the MaRDI Portal: lme4 has the software profile but no class; optimal control is a computational task
LME4, OPTIMAL_CONTROL = 'mardi:Q16687', 'mardi:Q6534338'


def test_a_portal_item_with_the_profile_only_is_offered(portal):
    portal('typed_item_id')
    assert [option['id'] for option in options('Software', LME4)] == [LME4]


def test_a_portal_item_of_the_class_the_profile_is_shared_with_is_not(portal):
    '''Algorithmic and computational tasks share the task profile.'''
    portal('typed_item_id')
    assert options('AlgorithmicProblem', OPTIMAL_CONTROL) == []
    assert [option['id'] for option in options('Task', OPTIMAL_CONTROL)] == [OPTIMAL_CONTROL]
