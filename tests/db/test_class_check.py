'''The class check of the dropdowns with recorded answers of QLever and Wikidata (#170).

Recorded in ``class_check`` (see tests/support/recordings.py); a change of the
answers' format would show here.
'''
import pytest

import MaRDMO.class_check as class_check
from MaRDMO.constants import WIKIDATA

SOFTWARE = ['Q7397']
# LAPACK and OpenBLAS are software, mass is not
ITEMS = ['Q642141', 'Q21155124', 'Q11423']
# Albert Einstein is a human; bacterial growth is not noise
HUMAN = ['Q5']


def test_qlever_tells_which_items_are_software(portal):
    portal('class_check')
    assert class_check.wikidata_matches(ITEMS, roots=SOFTWARE) == {'Q642141': True, 'Q21155124': True,
                                                                   'Q11423': False}


def test_qlever_tells_which_items_are_noise(portal):
    portal('class_check')
    assert class_check.wikidata_matches(['Q937', 'Q762045'], noise=HUMAN) == {'Q937': False, 'Q762045': True}


@pytest.fixture
def qlever_down(monkeypatch):
    '''QLever fails; Wikidata's endpoint answers (recorded).'''
    query_sparql = class_check.queries.query_sparql

    def without_qlever(query, endpoint, **kwargs):
        return None if endpoint == WIKIDATA['qlever'] else query_sparql(query, endpoint, **kwargs)
    monkeypatch.setattr(class_check.queries, 'query_sparql', without_qlever)


def test_wikidata_tells_the_same_if_qlever_fails(portal, qlever_down):
    portal('class_check')
    assert class_check.wikidata_matches(ITEMS, roots=SOFTWARE) == {'Q642141': True, 'Q21155124': True,
                                                                   'Q11423': False}
    assert class_check.wikidata_matches(['Q937', 'Q762045'], noise=HUMAN) == {'Q937': False, 'Q762045': True}
