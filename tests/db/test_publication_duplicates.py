'''Publications already on the MaRDI Portal: found by their DOI (#158).

A publication is the portal item with its DOI, whatever their labels: the
preview lists it with "Use this item" only (there is nothing to redefine;
a wrong DOI is corrected on its page), and the export stops at it.  A
publication with the label and description of a portal publication with
another DOI is another publication: it is created with its DOI in the
description (#183), which the preview says; if the portal has exactly that
label and description, it is that item.  The portal
has Hestenes and Stiefel's conjugate gradients as Q5814205 and Q6824795
(the lower QID is used) and Dijkstra's note as Q78129; the DOI searches
and DOIs were recorded (``publication_duplicates``), the lookups by label
and QID are given.
'''
import pytest
import requests
from rdmo.projects.models import Membership

from MaRDMO.core.constants import BASE_URI
from MaRDMO.duplicates import look_up
from MaRDMO.core.config import get_items
from MaRDMO.export.items import unique_items
from MaRDMO.payload import DocumentationProblem, GeneratePayload, PortalUnavailable
from MaRDMO.sources.portal import PortalItems
from tests.db.conftest import answer, save
from tests.support.html import attribute, element, elements, links, preview_page, text

ITEMS = get_items()
PUBLICATION = {'class': {ITEMS['scholarly article']}, 'community': set(), 'profile': set()}
HESTENES = ('10.6028/jres.049.044', 'Methods of Conjugate Gradients for Solving Linear Systems', 'article')
DIJKSTRA = ('A note on two problems in connexion with graphs', 'scientific article')
OTHER_DOI = '10.9999/mardmo.tests.other'
SEG1D_DOI = '10.21105/JOSS.02404'                      # on Wikidata only


def publication(index, external_id, name, description, doi, *extra):
    return [answer('publication', f'P{index + 1}', set_index=index),
            answer('publication/id', f'doi:{doi}', external_id=external_id, set_index=index),
            answer('publication/name', name, set_index=index),
            answer('publication/description', description, set_index=index),
            answer('publication/reference', doi, option='doi', set_index=index, collection_index=0),
            *extra]


@pytest.fixture
def model(project, client, django_user_model, monkeypatch):
    '''Three publications with their citation: Hestenes and Stiefel's (new), seg1d (Wikidata), and a new one named as Dijkstra's.

    With their citation (a title), the preview does not look them up (see test_preview_citations).
    '''
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    client.force_login(user)
    save(documentation,
         *publication(0, 'user:hestenes', HESTENES[1], HESTENES[2], HESTENES[0],
                      answer('publication/title', HESTENES[1], set_index=0),
                      answer('publication/author/name', 'Magnus R. Hestenes', set_index=0, collection_index=0)),
         *publication(1, 'wikidata:Q106245557', 'seg1d', 'scientific article published in 2020', SEG1D_DOI,
                      answer('publication/title', 'seg1d', set_index=1)),
         *publication(2, 'user:other', *DIJKSTRA, OTHER_DOI, answer('publication/title', DIJKSTRA[0], set_index=2)))
    return documentation


@pytest.fixture
def found(portal, monkeypatch):
    '''The DOI lookups recorded; the portal has Dijkstra's label and description (Q78129), and markers.'''
    portal('publication_duplicates')
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: PortalItems(
        by_label={DIJKSTRA: 'Q78129'}, markers={'Q5814205': PUBLICATION, 'Q78129': PUBLICATION}))


def rows(html):
    return {text(element(row, cls='mardmo-item__label')): row
            for row in elements(html, tag='li', cls='mardmo-duplicate')}


def test_publications_get_their_doi_as_items(model, client):
    from MaRDMO.main import MaRDMOExportProvider  # noqa: PLC0415
    provider = MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = model, None
    answers, _ = provider.get_post_data()
    items, _ = unique_items(answers)
    assert sorted(item['doi'] for item in items.values() if item.get('doi')) == sorted(
        [HESTENES[0], SEG1D_DOI, OTHER_DOI])


def test_the_preview_lists_a_publication_with_the_doi_of_a_portal_item(model, client, found):
    html = preview_page(client, model)
    listed = rows(html)
    # seg1d is not on the portal; the new publication named as Dijkstra's is another publication
    assert {name: attribute(row, 'data-action') for name, row in listed.items()} == {HESTENES[1]: 'reuse'}
    hestenes = listed[HESTENES[1]]
    assert [label for label, _ in links(element(hestenes, cls='mardmo-duplicate__portal'))] == ['Q5814205']
    # Only "Use this item": nothing to redefine, a wrong DOI is corrected on its page
    assert elements(hestenes, tag='input', cls='mardmo-decision__use')
    assert not elements(hestenes, tag='input', cls='mardmo-decision__redefine')
    assert 'The MaRDI Portal has this DOI as Q5814205: it is this publication.' in text(hestenes)
    # Created with its DOI in the description
    assert (f'Created as: {DIJKSTRA[0]} ({DIJKSTRA[1]} (DOI {OTHER_DOI})) — the MaRDI Portal has another '
            'publication with this title and description') in text(html)


def test_use_the_portal_publication(model, client, found):
    response = client.post(f'/services/reuse/{model.pk}/',
                           {'format': 'wikibase', 'item': 'user:hestenes', 'qid': 'Q5814205'})
    assert response.status_code == 302
    page = model.values.get(attribute__uri=f'{BASE_URI}domain/publication/id', set_index=0)
    assert page.external_id == 'mardi:Q5814205'
    name = model.values.get(attribute__uri=f'{BASE_URI}domain/publication/name', set_index=0).text
    assert name.startswith('Methods of conjugate gradients') and page.text.startswith(name)
    # The citation is the portal's now; the DOI stays
    assert not model.values.filter(set_index=0, attribute__uri__in=[
        f'{BASE_URI}domain/publication/title', f'{BASE_URI}domain/publication/author/name']).exists()
    assert model.values.get(attribute__uri=f'{BASE_URI}domain/publication/reference', set_index=0).text == HESTENES[0]


def test_another_publication_is_created_with_its_doi_in_the_description(found):
    payload = GeneratePayload('https://portal.mardi4nfdi.de', user_items={})
    (source, item), = items((DIJKSTRA[0], OTHER_DOI))
    item['Description'] = DIJKSTRA[1]
    payload._find_on_portal([(source, None, 'Item0', item)])
    assert item['create_as'] == f'{DIJKSTRA[1]} (DOI {OTHER_DOI})'


def test_a_portal_item_with_that_description_is_the_publication(model, client, found, monkeypatch):
    created = (DIJKSTRA[0], f'{DIJKSTRA[1]} (DOI {OTHER_DOI})')
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda pairs=(), **kwargs: PortalItems(
        by_label={pair: qid for pair, qid in {DIJKSTRA: 'Q78129', created: 'Q7'}.items() if pair in pairs},
        markers={'Q5814205': PUBLICATION, 'Q78129': PUBLICATION, 'Q7': PUBLICATION}))
    listed = rows(preview_page(client, model))
    assert attribute(listed[DIJKSTRA[0]], 'data-action') == 'reuse'
    assert [label for label, _ in links(element(listed[DIJKSTRA[0]], cls='mardmo-duplicate__portal'))] == ['Q7']


def items(*publications):
    return [('not found', {'ID': f'user:{index}', 'Name': name, 'Description': 'article', 'doi': doi})
            for index, (name, doi) in enumerate(publications)]


def test_the_export_stops_at_a_publication_on_the_portal(found):
    payload = GeneratePayload('https://portal.mardi4nfdi.de', user_items={})
    todo = [(source, None, f'Item{index}', item) for index, (source, item) in enumerate(items(
        ('conjugate gradients', HESTENES[0]), ('seg1d', SEG1D_DOI)))]
    with pytest.raises(DocumentationProblem) as problem:
        payload._find_on_portal(todo)
    assert [str(message) for message in problem.value.args] == [
        "'conjugate gradients' has the DOI 10.6028/jres.049.044, which the MaRDI Portal has as Q5814205: it is "
        "this publication. Use the portal item (in the preview), or correct the DOI."]


@pytest.fixture
def unreachable(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError('down')
    monkeypatch.setattr('MaRDMO.duplicates.find_publications_by_doi', fail)
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: PortalItems())


def test_a_failed_doi_lookup_is_noticed(unreachable):
    found_items, duplicates = look_up(items(('conjugate gradients', HESTENES[0])), (), None)
    assert found_items.doi_failed and duplicates == []
    with pytest.raises(PortalUnavailable):
        GeneratePayload('https://portal.mardi4nfdi.de', user_items={})._find_on_portal(
            [('not found', None, 'Item0', item) for _, item in items(('conjugate gradients', HESTENES[0]))])


def test_the_preview_asks_to_try_again_when_the_doi_lookup_failed(model, client, unreachable):
    assert 'could not check' in text(element(preview_page(client, model), id='portal-duplicates'))
