'''The portal is searched by the MaRDI profiles of a dropdown's classes (#170).

Most software on the portal has only the software profile, no class; the
portal's faceted search finds such items, as the portal's own search does.
Classes without a profile are searched by class; a profile several classes
share (tasks, quantities) leaves out the items of the classes a dropdown
does not search.
'''
import json
from pathlib import Path

import pytest
import requests

import MaRDMO.queries as queries
import MaRDMO.sources.portal as portal_api
import MaRDMO.sources.wikibase as wikibase
from MaRDMO.getters import get_items, get_properties
from MaRDMO.optionsets import PROFILES, PROVIDERS, Search

DATA = Path(queries.__file__).parent / 'data'


def test_every_class_and_profile_is_known_on_every_portal():
    for name in ('items.json', 'items_staging.json'):
        items = json.loads((DATA / name).read_text(encoding='utf-8'))
        assert not [key for pair in PROFILES.items() for key in pair if key not in items], name
    for name in ('properties.json', 'properties_staging.json'):
        assert 'MaRDI profile type' in json.loads((DATA / name).read_text(encoding='utf-8')), name


def test_a_shared_profile_leaves_out_the_other_class():
    assert PROVIDERS['AlgorithmicProblem'].profiles == ['MaRDI task profile']
    assert PROVIDERS['AlgorithmicProblem'].excluded_classes == ['computational task']
    assert PROVIDERS['Task'].excluded_classes == ['algorithmic task']
    # Quantities and quantity kinds together leave out nothing; one of them the other
    assert PROVIDERS['QuantityOrQuantityKind'].excluded_classes == []
    assert PROVIDERS['RelatedQuantityKindWithoutCreation'].excluded_classes == ['quantity']


def test_classes_without_a_profile_are_searched_by_class():
    assert Search('hardware', 'computer hardware').profiles == []
    assert Search('hardware', 'computer hardware').classes_without_profile == ['computer hardware']
    both = Search('both', ['software', 'benchmark'])
    assert (both.profiles, both.classes_without_profile) == (['MaRDI software profile'], ['benchmark'])
    assert Search('software', 'software').classes_without_profile == []


class Portal:
    '''Answers the portal's API: a profile search (pages) and wbgetentities.'''

    def __init__(self, monkeypatch, pages, entities):
        self.pages, self.entities, self.params = pages, entities, []
        monkeypatch.setattr(portal_api, 'request_with_retry', self)    # the profile search
        monkeypatch.setattr(wikibase, 'request_with_retry', self)    # wbgetentities

    def __call__(self, method, url, **kwargs):
        params = kwargs['params']
        self.params.append(params)
        response = requests.Response()
        response.status_code = 200
        body = ({'query': {'pages': self.pages}} if params.get('generator') == 'search'
                else {'entities': {qid: self.entities[qid] for qid in params['ids'].split('|')}})
        response._content = json.dumps(body).encode()
        return response


def entity(label, *classes):
    instance_of = get_properties()['instance of']
    return {'labels': {'en': {'value': label}}, 'descriptions': {'en': {'value': f'{label} item'}},
            'claims': {instance_of: [{'mainsnak': {'datavalue': {'value': {'id': qid}}}} for qid in classes]}}


def test_the_profile_search_finds_the_items_of_the_profile_pages_in_their_order(monkeypatch):
    items, properties = get_items(), get_properties()
    portal = Portal(monkeypatch, {
        '7': {'title': 'Lme4qtl', 'index': 2, 'pageprops': {'wikibase_item': 'Q2'}},
        '5': {'title': 'Lme4', 'index': 1, 'pageprops': {'wikibase_item': 'Q1'}},
        '9': {'title': 'A page without item', 'index': 3}}, {'Q1': entity('lme4'), 'Q2': entity('lme4qtl')})
    options = portal_api.query_api_per_profile('lme4', [items['MaRDI software profile'], items['MaRDI algorithm profile']])
    assert options == [{'id': 'mardi:Q1', 'text': 'lme4 (lme4 item)'}, {'id': 'mardi:Q2', 'text': 'lme4qtl (lme4qtl item)'}]
    search, labels = portal.params
    # Several profiles: facets separated by a space (alternatives); the pages are in namespace 0
    profile = properties['MaRDI profile type']
    assert search['gsrsearch'] == (f'lme4* haswbfacet:{profile}={items["MaRDI software profile"]} '
                                   f'haswbfacet:{profile}={items["MaRDI algorithm profile"]}')
    assert (search['gsrnamespace'], search['ppprop']) == (0, 'wikibase_item')
    # Without a class to leave out, the classes are not fetched
    assert labels['props'] == 'labels|descriptions'


def test_a_shared_profile_leaves_out_the_items_of_the_other_class(monkeypatch):
    items = get_items()
    computational, algorithmic = items['computational task'], items['algorithmic task']
    portal = Portal(monkeypatch, {
        '1': {'index': 1, 'pageprops': {'wikibase_item': 'Q1'}},
        '2': {'index': 2, 'pageprops': {'wikibase_item': 'Q2'}},
        '3': {'index': 3, 'pageprops': {'wikibase_item': 'Q3'}}},
        {'Q1': entity('sorting', algorithmic), 'Q2': entity('simulation', computational), 'Q3': entity('no class')})
    options = portal_api.query_api_per_profile('s', [items['MaRDI task profile']], exclude=[computational])
    assert [option['id'] for option in options] == ['mardi:Q1', 'mardi:Q3']
    assert portal.params[1]['props'] == 'labels|descriptions|claims'


@pytest.fixture
def searches(monkeypatch):
    calls = []

    def by_class(term, item_class, raise_errors=False):
        calls.append(('class', item_class))
        return [{'id': f'mardi:C{n}', 'text': f'class {n}'} for n in range(30)] + [{'id': 'mardi:Q0', 'text': 'both'}]

    def by_profile(term, profiles, exclude=None, raise_errors=False):
        calls.append(('profile', profiles, exclude))
        return [{'id': 'mardi:Q0', 'text': 'both'}] + [{'id': f'mardi:P{n}', 'text': f'profile {n}'} for n in range(30)]
    monkeypatch.setattr(queries, 'query_api_per_class', by_class)
    monkeypatch.setattr(queries, 'query_api_per_profile', by_profile)
    return calls


def test_classes_with_a_profile_are_searched_by_it_only(searches):
    queries.query_sources('s', None, sources=['mardi'], not_found=False, profiles=['Q9'], exclude=['Q8'])
    assert searches == [('profile', ['Q9'], ['Q8'])]


def test_a_dropdown_of_both_kinds_searches_both_and_takes_them_in_turns(searches):
    options = queries.query_sources('s', 'Q7', sources=['mardi'], not_found=False, profiles=['Q9'])
    ids = [option['id'] for option in options]
    assert sorted(searches) == [('class', 'Q7'), ('profile', ['Q9'], None)]
    # The first 25 have hits of both searches, each once
    assert len(ids) == 25 == len(set(ids))
    assert sum(qid.startswith('mardi:C') for qid in ids) >= 12 and sum(qid.startswith('mardi:P') for qid in ids) >= 11


def test_without_profiles_the_portal_is_searched_by_class_as_before(searches):
    queries.query_sources('s', 'Q7', sources=['mardi'], not_found=False)
    assert searches == [('class', 'Q7')]


def test_the_cache_keeps_searches_with_other_profiles_apart(searches):
    queries.query_sources('s', None, sources=['mardi'], not_found=False, profiles=['Q9'])
    queries.query_sources('s', None, sources=['mardi'], not_found=False, profiles=['Q9'], exclude=['Q8'])
    queries.query_sources('s', None, sources=['mardi'], not_found=False, profiles=['Q9'])
    assert searches == [('profile', ['Q9'], None), ('profile', ['Q9'], ['Q8'])]
