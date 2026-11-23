'''The class check of the dropdowns with recorded answers of QLever and Wikidata (#170).

Recorded in ``class_check`` (see tests/support/recordings.py); a change of the
answers' format would show here.
'''
import pytest

import MaRDMO.sources.wikidata as wikidata_api
import MaRDMO.components.dropdowns as dropdowns
from MaRDMO.core.constants import WIKIDATA
from MaRDMO.core.searches import PROVIDERS

SOFTWARE = ['Q7397']
# LAPACK and OpenBLAS are software, mass is not
ITEMS = ['Q642141', 'Q21155124', 'Q11423']
# Albert Einstein is a human; bacterial growth is not noise
HUMAN = ['Q5']


def test_qlever_tells_which_items_are_software(portal):
    portal('class_check')
    assert wikidata_api.wikidata_matches(ITEMS, roots=SOFTWARE) == {'Q642141': True, 'Q21155124': True,
                                                                   'Q11423': False}


def test_qlever_tells_which_items_are_noise(portal):
    portal('class_check')
    assert wikidata_api.wikidata_matches(['Q937', 'Q762045'], noise=HUMAN) == {'Q937': False, 'Q762045': True}


@pytest.fixture
def qlever_down(monkeypatch):
    '''QLever fails; Wikidata's endpoint answers (recorded).'''
    query_sparql = wikidata_api.http.query_sparql

    def without_qlever(query, endpoint, **kwargs):
        return None if endpoint == WIKIDATA['qlever'] else query_sparql(query, endpoint, **kwargs)
    monkeypatch.setattr(wikidata_api.http, 'query_sparql', without_qlever)


def test_the_software_dropdown_offers_wikidata_software_only(portal):
    '''Wikidata's 50 hits for MATLAB are mostly places and people named Matlab; software stays.'''
    portal('class_check')
    options = dropdowns.query_sources('MATLAB', sources=['wikidata'], not_found=False,
                                    roots=PROVIDERS['Software'].wikidata_roots)
    texts = [option['text'] for option in options]
    assert any(text.startswith('MATLAB (') for text in texts), texts
    assert not any('Upazila' in text or 'Abdullayev' in text for text in texts), texts
    assert all(option['id'].startswith('wikidata:') for option in options)


# The Wikidata twins of the portal's research problems (2026-11-20): none is noise
RESEARCH_PROBLEMS = [
    'Q10429773',   # biological wastewater treatment
    'Q104536208',  # ligand-receptor interaction
    'Q108033749',  # image denoising
    'Q1234926',    # molecular rotation (no class)
    'Q127006',     # muscle contraction
    'Q17050218',   # gas separation (no class)
    'Q177625',     # electromagnetic field
    'Q1943412',    # molecular spectroscopy
    'Q20127660',   # wastewater treatment
    'Q3151656',    # Taylor–Couette flow
    'Q488071',     # electric discharge
    'Q762045',     # bacterial growth
    'Q829360',     # pendulum
    'Q900121',     # molecular vibrations
    'Q901663',     # molecular dynamics simulation
]
# Albert Einstein, an article, the film and an album "Turbulence"
NOISE = ['Q937', 'Q37198983', 'Q727775', 'Q3542269']


def test_the_research_problems_on_the_portal_are_not_noise(portal):
    portal('class_check')
    matches = wikidata_api.wikidata_matches(RESEARCH_PROBLEMS + NOISE,
                                           noise=PROVIDERS['ResearchProblem'].wikidata_noise)
    assert [qid for qid in RESEARCH_PROBLEMS if not matches[qid]] == []
    assert [qid for qid in NOISE if matches[qid]] == []


def test_the_research_problem_dropdown_leaves_out_films_and_albums(portal):
    portal('class_check')
    options = dropdowns.query_sources('turbulence', sources=['wikidata'], not_found=False,
                                    noise=PROVIDERS['ResearchProblem'].wikidata_noise)
    ids = [option['id'] for option in options]
    assert 'wikidata:Q190132' in ids, [option['text'] for option in options]  # turbulence
    assert 'wikidata:Q727775' not in ids and 'wikidata:Q3542269' not in ids


def test_wikidata_tells_the_same_if_qlever_fails(portal, qlever_down):
    portal('class_check')
    assert wikidata_api.wikidata_matches(ITEMS, roots=SOFTWARE) == {'Q642141': True, 'Q21155124': True,
                                                                   'Q11423': False}
    assert wikidata_api.wikidata_matches(['Q937', 'Q762045'], noise=HUMAN) == {'Q937': False, 'Q762045': True}


def test_without_qlever_scholarly_articles_are_noise_too(portal, qlever_down):
    '''Wikidata's main endpoint does not have them; research problems without a class it has.'''
    portal('class_check')
    matches = wikidata_api.wikidata_matches(RESEARCH_PROBLEMS + NOISE,
                                           noise=PROVIDERS['ResearchProblem'].wikidata_noise)
    assert [qid for qid in RESEARCH_PROBLEMS if not matches[qid]] == []
    assert [qid for qid in NOISE if matches[qid]] == []
