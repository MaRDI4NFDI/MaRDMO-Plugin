'''Which Wikidata items fit a dropdown, by their classes (#170): the query, the endpoints, the cache.'''
import logging

import pytest

import MaRDMO.sources.wikidata as wikidata_api
from MaRDMO.core.constants import WIKIDATA


class Endpoints:
    '''Stands in for query_sparql: answers per endpoint (QIDs found, or None for a failure); notes the calls.'''

    def __init__(self, monkeypatch, qlever=(), wikidata=()):
        self.answers = {WIKIDATA['qlever']: qlever, WIKIDATA['sparql']: wikidata}
        self.calls = []
        monkeypatch.setattr(wikidata_api.sparql, 'query_sparql', self)

    def __call__(self, query, endpoint, strict=False, waits=(), deadline=None):
        self.calls.append((endpoint, query, deadline))
        found = self.answers[endpoint]
        if found is None:
            return None
        return [{'item': {'value': f'http://www.wikidata.org/entity/{qid}'}} for qid in found]

    def endpoints(self):
        return [endpoint for endpoint, _, _ in self.calls]


def test_the_roots_query_walks_upwards_from_the_items_classes():
    query = wikidata_api.query_roots(['Q2', 'Q1'], ['Q7397'])
    assert 'VALUES ?item { wd:Q1 wd:Q2 }' in query and 'VALUES ?root { wd:Q7397 }' in query
    assert '{ ?item wdt:P31 ?class . } UNION { ?item wdt:P279 ?class . }' in query
    assert '?class wdt:P279* ?root .' in query and 'hint:' not in query
    # Wikidata's endpoint is told the direction; downwards from a broad root takes many seconds
    assert '?class wdt:P279* ?root . hint:Prior hint:gearing "forward" .' in wikidata_api.query_roots(
        ['Q1'], ['Q7397'], wikidata=True)


def test_the_noise_query_asks_for_instances_of_a_noise_class_or_its_subclasses():
    query = wikidata_api.query_noise(['Q1'], ['Q5', 'Q11424'])
    assert '?item wdt:P31 ?class .' in query and 'P279 ?class' not in query
    assert '?class wdt:P279* ?noise .' in query and 'VALUES ?noise { wd:Q11424 wd:Q5 }' in query
    assert 'dateModified' not in query


def test_on_wikidatas_endpoint_an_item_it_does_not_know_is_noise_too():
    '''Scholarly articles are not in its main graph; an item without a class is.'''
    query = wikidata_api.query_noise(['Q1'], ['Q5'], wikidata=True)
    assert 'OPTIONAL { ?item schema:dateModified ?modified . }' in query
    assert 'FILTER(!BOUND(?modified) || BOUND(?noise))' in query
    assert '?class wdt:P279* ?noise . hint:Prior hint:gearing "forward" .' in query


def test_qlever_answers_and_wikidata_is_not_asked(monkeypatch):
    endpoints = Endpoints(monkeypatch, qlever=['Q1'])
    assert wikidata_api.wikidata_matches(['Q1', 'Q2'], roots=['Q7397']) == {'Q1': True, 'Q2': False}
    assert endpoints.endpoints() == [WIKIDATA['qlever']]
    endpoint, query, deadline = endpoints.calls[0]
    # QLever's query has the prefixes; its answer is waited for briefly only
    assert query.startswith(wikidata_api.PREFIXES) and 'hint:' not in query
    assert deadline - wikidata_api.time.monotonic() <= wikidata_api.QLEVER_TIMEOUT


def test_wikidata_is_asked_if_qlever_fails(monkeypatch, caplog):
    endpoints = Endpoints(monkeypatch, qlever=None, wikidata=['Q2'])
    with caplog.at_level(logging.WARNING, logger='MaRDMO.sources.wikidata'):
        assert wikidata_api.wikidata_matches(['Q1', 'Q2'], roots=['Q7397']) == {'Q1': False, 'Q2': True}
    assert endpoints.endpoints() == [WIKIDATA['qlever'], WIKIDATA['sparql']]
    assert 'hint:gearing "forward"' in endpoints.calls[1][1]
    assert 'QLever failed' in caplog.text


def test_if_both_fail_there_is_no_answer_and_nothing_is_cached(monkeypatch, caplog):
    endpoints = Endpoints(monkeypatch, qlever=None, wikidata=None)
    with caplog.at_level(logging.WARNING, logger='MaRDMO.sources.wikidata'):
        assert wikidata_api.wikidata_matches(['Q1'], roots=['Q7397']) is None
    assert 'not filtered' in caplog.text
    # The next search tries again
    endpoints.answers[WIKIDATA['qlever']] = ['Q1']
    assert wikidata_api.wikidata_matches(['Q1'], roots=['Q7397']) == {'Q1': True}
    assert endpoints.endpoints().count(WIKIDATA['qlever']) == 2


def test_checked_items_are_not_checked_again(monkeypatch):
    endpoints = Endpoints(monkeypatch, qlever=['Q1'])
    wikidata_api.wikidata_matches(['Q1', 'Q2'], roots=['Q7397'])
    assert wikidata_api.wikidata_matches(['Q2', 'Q1', 'Q3'], roots=['Q7397']) == {'Q2': False, 'Q1': True,
                                                                                  'Q3': False}
    # Only the new item is asked for
    assert 'VALUES ?item { wd:Q3 }' in endpoints.calls[1][1]
    # Nothing new: no request
    wikidata_api.wikidata_matches(['Q3', 'Q1'], roots=['Q7397'])
    assert len(endpoints.calls) == 2


def test_the_same_item_is_checked_again_for_other_classes(monkeypatch):
    endpoints = Endpoints(monkeypatch, qlever=['Q1'])
    wikidata_api.wikidata_matches(['Q1'], roots=['Q7397'])
    endpoints.answers[WIKIDATA['qlever']] = []
    assert wikidata_api.wikidata_matches(['Q1'], roots=['Q9143']) == {'Q1': False}
    # Roots and noise with the same classes are different checks, too
    assert wikidata_api.wikidata_matches(['Q1'], noise=['Q7397']) == {'Q1': True}
    assert len(endpoints.calls) == 3


def test_with_noise_the_items_found_do_not_fit(monkeypatch):
    Endpoints(monkeypatch, qlever=['Q937'])
    assert wikidata_api.wikidata_matches(['Q937', 'Q762045'], noise=['Q5']) == {'Q937': False, 'Q762045': True}


def test_wikidata_ids_duplicates_and_no_items(monkeypatch):
    endpoints = Endpoints(monkeypatch, qlever=['Q1'])
    assert wikidata_api.wikidata_matches([], roots=['Q7397']) == {}
    assert not endpoints.calls
    assert wikidata_api.wikidata_matches(['wikidata:Q1', 'Q1', 'wikidata:Q2'], roots=['Q7397']) == {'Q1': True,
                                                                                                   'Q2': False}
    assert 'VALUES ?item { wd:Q1 wd:Q2 }' in endpoints.calls[0][1]


def test_what_is_not_a_qid_does_not_fit_and_is_not_asked_for(monkeypatch):
    endpoints = Endpoints(monkeypatch, qlever=[])
    matches = wikidata_api.wikidata_matches(['Q1', 'Q0', 'q2', 'Q3 } . ?x ?y ?z {', 'mardi:Q4'], roots=['Q7397'])
    assert matches == {'Q1': False, 'Q0': False, 'q2': False, 'Q3 } . ?x ?y ?z {': False, 'mardi:Q4': False}
    assert 'VALUES ?item { wd:Q1 }' in endpoints.calls[0][1]


@pytest.mark.parametrize('arguments', [{}, {'roots': ['Q1'], 'noise': ['Q2']}, {'roots': ['Q1 }']},
                                       {'noise': ['P31']}])
def test_roots_or_noise_and_only_qids(arguments):
    with pytest.raises(ValueError):
        wikidata_api.wikidata_matches(['Q1'], **arguments)
