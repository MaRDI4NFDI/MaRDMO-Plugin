'''Typing mardi:Q… or wikidata:Q… into a dropdown offers that item, if it fits the dropdown (#170).'''
import pytest
import requests

import MaRDMO.queries as queries
from MaRDMO.getters import get_items, get_properties
from MaRDMO.providers import MaRDMOProvider


@pytest.mark.parametrize('text, expected', [
    ('mardi:Q123', ('mardi', 'Q123')), ('wikidata:Q42', ('wikidata', 'Q42')),
    ('MaRDI:q5', ('mardi', 'Q5')), (' Wikidata : Q42 ', ('wikidata', 'Q42')),
])
def test_an_item_id_is_recognised_in_any_case(text, expected):
    assert queries.typed_item_id(text) == expected


@pytest.mark.parametrize('text', ['Q42', 'wikidata:Q0', 'wikidata:Q42 mass', 'mardi:P31', 'doi:10.1/x',
                                  'https://www.wikidata.org/wiki/Q42', 'wiki:Q42', 'mass', ''])
def test_anything_else_is_a_search_text(text):
    assert queries.typed_item_id(text) is None


def entity(qid, label, classes=(), profiles=(), **extra):
    properties = get_properties()

    def claims(values):
        return [{'mainsnak': {'datavalue': {'value': {'id': value}}}} for value in values]
    return {'id': qid, 'labels': {'en': {'value': label}}, 'descriptions': {'en': {'value': f'{label} item'}},
            'claims': {properties['instance of']: claims(classes), properties['MaRDI profile type']: claims(profiles)},
            **extra}


@pytest.fixture
def portal(monkeypatch):
    '''_entities answers from a dict ({QID: entity}); an exception is raised.'''
    asked = []

    def use(answers):
        def entities(source, qids, props, waits=(), deadline=None):
            asked.append((source, qids, props))
            if isinstance(answers, Exception):
                raise answers
            return {qid: answers[qid] for qid in qids if qid in answers}
        monkeypatch.setattr(queries, '_entities', entities)
        return asked
    return use


def test_a_portal_item_of_the_class_or_with_the_profile_fits(portal):
    items = get_items()
    software, profile = items['software'], items['MaRDI software profile']
    portal({'Q1': entity('Q1', 'LAPACK', classes=[software]), 'Q2': entity('Q2', 'lme4', profiles=[profile]),
            'Q3': entity('Q3', 'pendulum', classes=[items['research problem']])})
    fits = [queries.item_by_id('mardi', qid, classes=[software], profiles=[profile]) for qid in ('Q1', 'Q2', 'Q3')]
    assert fits[0] == [{'id': 'mardi:Q1', 'text': 'LAPACK (LAPACK item)', 'help': fits[0][0]['help']}]
    assert fits[1][0]['id'] == 'mardi:Q2' and fits[2] == []


def test_a_portal_item_of_a_class_left_out_does_not_fit(portal):
    items = get_items()
    portal({'Q1': entity('Q1', 'simulation', classes=[items['computational task']],
                         profiles=[items['MaRDI task profile']])})
    assert queries.item_by_id('mardi', 'Q1', classes=[items['algorithmic task']],
                              profiles=[items['MaRDI task profile']], exclude=[items['computational task']]) == []


def test_a_merged_item_is_offered_as_the_one_it_was_merged_into(portal):
    software = get_items()['software']
    portal({'Q1': entity('Q9', 'LAPACK', classes=[software], redirects={'from': 'Q1', 'to': 'Q9'})})
    assert queries.item_by_id('mardi', 'Q1', classes=[software])[0]['id'] == 'mardi:Q9'


def test_a_missing_item_or_a_failed_lookup_offers_nothing(portal):
    portal({'Q1': {'id': 'Q1', 'missing': ''}})
    assert queries.item_by_id('mardi', 'Q1', classes=['Q5']) == []
    portal(requests.exceptions.ConnectionError('down'))
    assert queries.item_by_id('mardi', 'Q1', classes=['Q5']) == []


@pytest.fixture
def matches(monkeypatch):
    def use(answer):
        def wikidata_matches(items, roots=None, noise=None, deadline=None):
            return None if answer is None else {item: answer for item in items}
        monkeypatch.setattr(queries, 'wikidata_matches', wikidata_matches)
    return use


def test_a_wikidata_item_fits_as_a_search_hit_does(portal, matches):
    asked = portal({'Q42': entity('Q42', 'MATLAB')})
    matches(True)
    assert queries.item_by_id('wikidata', 'Q42', roots=['Q7397'])[0]['id'] == 'wikidata:Q42'
    # Its classes are checked by SPARQL, not fetched
    assert asked[0] == ('wikidata', ['Q42'], 'labels|descriptions')
    matches(False)
    assert queries.item_by_id('wikidata', 'Q42', roots=['Q7397']) == []
    assert queries.item_by_id('wikidata', 'Q42', noise=['Q5']) == []
    # If the check fails, it is offered, as unfiltered hits are
    matches(None)
    assert queries.item_by_id('wikidata', 'Q42', roots=['Q7397'])[0]['id'] == 'wikidata:Q42'


@pytest.fixture
def searched(monkeypatch):
    '''The provider's searches are recorded; item_by_id answers with its arguments.'''
    calls = []
    monkeypatch.setattr('MaRDMO.providers.query_sources', lambda **kwargs: calls.append('search') or [])
    monkeypatch.setattr('MaRDMO.providers.query_sources_with_user_additions',
                        lambda **kwargs: calls.append('search') or [])
    monkeypatch.setattr('MaRDMO.providers.item_by_id',
                        lambda source, qid, **kwargs: calls.append((source, qid, kwargs)) or [{'id': f'{source}:{qid}'}])
    return calls


def test_the_dropdown_offers_the_item_named_and_nothing_else(searched):
    provider = MaRDMOProvider('RelatedSoftwareWithCreation', 'software', 'MaRDMO.providers.MaRDMOProvider')
    # Not "new item", not the text as an item to create
    assert provider.get_options(None, search='Wikidata:Q42') == [{'id': 'wikidata:Q42'}]
    (source, qid, arguments), = searched
    items = get_items()
    assert (source, qid, arguments['roots']) == ('wikidata', 'Q42', ['Q7397'])
    assert arguments['classes'] == [items['software']] and arguments['profiles'] == [items['MaRDI software profile']]


def test_a_dropdown_without_wikidata_offers_no_wikidata_item(searched):
    provider = MaRDMOProvider('RelatedAlgorithmWithoutCreation', 'algorithm', 'MaRDMO.providers.MaRDMOProvider')
    assert provider.get_options(None, search='wikidata:Q42') == []
    assert provider.get_options(None, search='mardi:Q7')[0]['id'] == 'mardi:Q7'
    assert [call[0] for call in searched] == ['mardi']
