'''The portal's software without a class is found by its profile (#170), recorded (``portal_profiles``).

lme4 (an R package) has the software profile but no class; the search by
class finds no software for "lme4", the search by profile finds it.
'''
import MaRDMO.sources.portal as portal_api
from MaRDMO.getters import get_items
from MaRDMO.optionsets import PROVIDERS

LME4 = 'mardi:Q16687'


def test_software_without_a_class_is_found_by_its_profile(portal):
    portal('portal_profiles')
    items = get_items()
    assert LME4 not in [option['id'] for option in portal_api.query_api_per_class('lme4', items['software'],
                                                                                 raise_errors=True)]
    options = portal_api.query_api_per_profile('lme4', [items[name] for name in PROVIDERS['Software'].profiles],
                                            raise_errors=True)
    assert LME4 in [option['id'] for option in options], options
    assert all(option['id'].startswith('mardi:Q') for option in options)


def test_the_algorithmic_task_dropdown_leaves_out_computational_tasks(portal):
    portal('portal_profiles')
    items = get_items()
    search = PROVIDERS['AlgorithmicProblem']
    options = portal_api.query_api_per_profile('task', [items[name] for name in search.profiles],
                                            [items[name] for name in search.excluded_classes], raise_errors=True)
    everything = portal_api.query_api_per_profile('task', [items[name] for name in search.profiles], raise_errors=True)
    assert options and len(options) < len(everything)
