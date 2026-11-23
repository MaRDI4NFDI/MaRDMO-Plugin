'''Wikidata publications of a filled page become their portal items, where there are some (#158).

An item filled from Wikidata brings its publications as Wikidata items.  One
the MaRDI Portal has too becomes the portal item: the portal item with its
Wikidata QID (P12), else the portal publication with its DOI.  The portal
has Hestenes and Stiefel's conjugate gradients twice, Q5814205 with the
Wikidata QID and the DOI in upper case and Q6824795 without QID and the DOI
in lower case; Dijkstra's note is Q78129 with its QID.  A publication
without DOI, or not on the portal, stays the Wikidata item.  The answers of
the portal and Wikidata were recorded (``publication_twins``).
'''
import pytest
import requests

from MaRDMO.core.constants import BASE_URI
from MaRDMO.handler_base import publication_twins
from MaRDMO.model.handlers import Information
from MaRDMO.core.models import Relatant
from MaRDMO.sources.portal import portal_publications_by_doi
from MaRDMO.sources.wikidata import wikidata_dois

DIJKSTRA = Relatant('wikidata:Q21694527', 'A note on two problems in connexion with graphs', 'scientific article')
HESTENES = Relatant('wikidata:Q55882088', 'Methods of conjugate gradients for solving linear systems',
                    'scientific article published in 1952')
ELEMENTS = Relatant('wikidata:Q172891', "Euclid's Elements", 'mathematical treatise by Euclid')   # no DOI


@pytest.fixture
def recorded(portal):
    portal('publication_twins')


@pytest.fixture
def no_qid_twins(monkeypatch):
    '''The portal knows no twin by Wikidata QID: only the DOI finds one.'''
    monkeypatch.setattr('MaRDMO.handler_base.portal_twins', lambda relatants, markers: {})


def test_the_dois_of_wikidata_publications(recorded):
    assert wikidata_dois(['Q55882088', 'Q21694527', 'Q172891']) == {
        'Q55882088': '10.6028/JRES.049.044', 'Q21694527': '10.1007/BF01386390'}


def test_portal_publications_by_doi_whatever_the_case(recorded):
    found = portal_publications_by_doi(['10.6028/jres.049.044', '10.1007/BF01386390', '10.9999/mardmo.tests.nowhere'])
    # Of the two items with Hestenes and Stiefel's DOI the one with the lower QID
    assert {doi: qid for doi, (qid, _, _) in found.items()} == {
        '10.6028/JRES.049.044': 'Q5814205', '10.1007/BF01386390': 'Q78129'}
    assert found['10.1007/BF01386390'][1] == 'A note on two problems in connexion with graphs'


def test_a_wikidata_publication_with_a_portal_twin(recorded):
    twin, = publication_twins([DIJKSTRA])
    assert twin.id == 'mardi:Q78129' and twin.label == 'A note on two problems in connexion with graphs'


def test_a_wikidata_publication_found_on_the_portal_by_its_doi(recorded, no_qid_twins):
    twin, elements = publication_twins([HESTENES, ELEMENTS])
    assert twin.id == 'mardi:Q5814205' and twin.label.startswith('Methods of conjugate gradients')
    # No DOI: stays the Wikidata item
    assert elements == ELEMENTS


def test_publications_of_the_portal_and_on_pages_are_kept(monkeypatch):
    monkeypatch.setattr('MaRDMO.handler_base.portal_twins', lambda *args: pytest.fail('looked up'))
    publications = [Relatant('mardi:Q78129', 'a', 'b'), DIJKSTRA]
    assert publication_twins(publications, visited={DIJKSTRA.id}) == publications


def test_a_failed_lookup_keeps_the_wikidata_publications(no_qid_twins, monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError('down')
    monkeypatch.setattr('MaRDMO.sources.portal.request_with_retry', fail)
    monkeypatch.setattr('MaRDMO.sources.wikibase.request_with_retry', fail)
    assert portal_publications_by_doi(['10.1007/BF01386390']) == {}
    assert publication_twins([HESTENES]) == [HESTENES]
    assert 'Could not look up the DOIs of Wikidata publications' in caplog.text


def test_the_page_of_a_wikidata_publication_is_the_portal_item(project, recorded, no_qid_twins, monkeypatch):
    filled = []
    monkeypatch.setattr('MaRDMO.publication.handlers.Information.fill_citations',
                        lambda self, project, entries, catalog='', snapshot=None: filled.extend(entries))
    documentation = project('mardmo-model-catalog')
    Information()._hydrate_publications(documentation, [HESTENES, ELEMENTS], 'mardmo-model-catalog', set())
    pages = sorted(documentation.values.filter(attribute__uri=f'{BASE_URI}domain/publication/id')
                   .values_list('set_index', 'external_id', 'text'))
    assert [(index, external_id) for index, external_id, _ in pages] == [(0, 'mardi:Q5814205'), (1, ELEMENTS.id)]
    assert pages[0][2].startswith('Methods of conjugate gradients')
    # Filled from the portal
    assert [external_id for _, external_id, _ in filled] == ['mardi:Q5814205', ELEMENTS.id]


def test_a_doi_the_portal_has_percent_encoded(recorded):
    lorenz = '10.1175/1520-0469(1963)020<0130:DNF>2.0.CO;2'
    found = portal_publications_by_doi([lorenz])
    assert {doi: qid for doi, (qid, _, _) in found.items()} == {lorenz.upper(): 'Q4608560'}
