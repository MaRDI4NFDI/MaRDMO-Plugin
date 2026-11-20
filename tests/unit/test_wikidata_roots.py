'''The dropdowns offer only the Wikidata items of their classes (#170): the roots, and the filter.'''
import pytest

import MaRDMO.class_check as class_check
import MaRDMO.queries as queries
from MaRDMO.optionsets import NO_WIKIDATA, NOISE_FILTERED, PROVIDERS, WIKIDATA_NOISE, WIKIDATA_ROOTS, Search

WIKIDATA_ROWS = [key for key, search in PROVIDERS.items()
                 if not search.by_identifier and 'wikidata' in (search.search_sources or ['wikidata'])]


def hit(qid, label):
    return {'id': qid, 'display': {'label': {'value': label}, 'description': {'value': f'{label} item'}}}


def test_every_class_searched_on_wikidata_has_roots_or_is_left_out_on_purpose():
    '''A forgotten class would offer its Wikidata hits unfiltered.'''
    for key in WIKIDATA_ROWS:
        for name in PROVIDERS[key].classes:
            assert name in WIKIDATA_ROOTS or name in NO_WIKIDATA | NOISE_FILTERED, (key, name)
    classes = [root for roots in WIKIDATA_ROOTS.values() for root in roots] + WIKIDATA_NOISE
    assert all(qid.startswith('Q') and qid[1:].isdigit() for qid in classes)
    assert not (set(WIKIDATA_ROOTS) & (NO_WIKIDATA | NOISE_FILTERED))
    assert len(set(WIKIDATA_NOISE)) == len(WIKIDATA_NOISE)


def test_no_row_mixes_classes_filtered_by_noise_and_by_roots():
    '''Such a row would be filtered by noise only (Search.noise_filtered).'''
    for key in WIKIDATA_ROWS:
        classes = set(PROVIDERS[key].classes)
        assert not (classes & NOISE_FILTERED and classes - NOISE_FILTERED - NO_WIKIDATA), key


def test_a_row_of_several_classes_filters_by_the_roots_of_all():
    search = PROVIDERS['QuantityOrQuantityKind']
    assert search.wikidata_roots == sorted(set(WIKIDATA_ROOTS['quantity']) | set(WIKIDATA_ROOTS['kind of quantity']))
    assert Search('both', ['software', 'benchmark']).wikidata_roots == ['Q7397', 'Q816747']


def test_process_steps_are_not_searched_on_wikidata():
    assert PROVIDERS['ProcessStep'].search_sources == ['mardi']
    assert PROVIDERS['RelatedStepWithCreation'].search_sources == ['mardi']
    assert 'ProcessStep' not in WIKIDATA_ROWS
    # A class Wikidata has nothing for adds no roots to the others
    assert Search('mixed', ['process step', 'data set']).wikidata_roots == WIKIDATA_ROOTS['data set']
    assert Search('mixed', ['process step', 'data set']).search_sources is None


def test_research_problems_are_filtered_by_noise():
    '''No Wikidata class fits them (phenomena, processes, …); what is never one is left out.'''
    for key in ('ResearchProblem', 'RelatedResearchProblemWithCreation'):
        assert PROVIDERS[key].wikidata_roots is None and PROVIDERS[key].wikidata_noise == WIKIDATA_NOISE
    assert PROVIDERS['Software'].wikidata_noise is None


@pytest.fixture
def matches(monkeypatch):
    '''wikidata_matches answers from a dict; None: the check failed.'''
    calls = []

    def answer(answers):
        def wikidata_matches(items, roots=None, noise=None, deadline=None):
            calls.append((list(items), roots))
            return None if answers is None else {item: answers.get(item, False) for item in items}
        monkeypatch.setattr(class_check, 'wikidata_matches', wikidata_matches)
        return calls
    return answer


def test_the_hits_of_the_classes_stay_in_their_order(matches):
    calls = matches({'Q3': True, 'Q1': True})
    hits = [hit('Q1', 'one'), hit('Q2', 'two'), hit('Q3', 'three'), {'no': 'id'}]
    assert queries.wikidata_hits(hits, ['Q7397']) == [hits[0], hits[2]]
    assert calls == [(['Q1', 'Q2', 'Q3'], ['Q7397'])]


def test_with_noise_the_hits_that_are_not_noise_stay(matches):
    calls = matches({'Q2': True})
    hits = [hit('Q1', 'a film'), hit('Q2', 'a phenomenon')]
    assert queries.wikidata_hits(hits, None, ['Q11424']) == [hits[1]]
    assert calls == [(['Q1', 'Q2'], None)]


def test_unfiltered_or_after_a_failed_check_the_first_ten_hits(matches):
    hits = [hit(f'Q{n}', f'item {n}') for n in range(1, 51)]
    calls = matches(None)
    assert queries.wikidata_hits(hits, ['Q7397']) == hits[:10]
    assert queries.wikidata_hits(hits, None) == hits[:10]
    # Without roots nothing is checked
    assert len(calls) == 1


def test_a_dropdown_asks_for_fifty_hits_and_offers_those_of_its_classes(matches, monkeypatch):
    matches({'Q2': True})
    searched = []

    def query_api(api_url, search_term, **kwargs):
        searched.append(kwargs['limit'])
        return [hit('Q1', 'alpha snake'), hit('Q2', 'alpha software')]
    monkeypatch.setattr(queries, 'query_api', query_api)
    options = queries.query_sources('alpha', sources=['wikidata'], not_found=False, roots=['Q7397'])
    assert [option['id'] for option in options] == ['wikidata:Q2'] and searched == [50]
