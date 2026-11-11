'''The ID dropdown of a page offers "new item" (#119); own items are known by their ID, not by that text.'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

import MaRDMO.queries as queries
from MaRDMO.adders import add_entities
from MaRDMO.constants import BASE_URI
from MaRDMO.ids import is_user_id
from MaRDMO.models import Relatant
from tests.db.conftest import answer, save


@pytest.fixture
def interview(project, client, django_user_model):
    '''A project of *catalog*; *edit* changes an answer as the interview does (RDMO's project value API).'''
    user = django_user_model.objects.create_user('owner', password='owner')
    client.force_login(user)

    def open_project(catalog='mardmo-model-catalog'):
        documentation = project(catalog)
        Membership.objects.create(project=documentation, user=user, role='owner')

        def edit(path, text, external_id, **index):
            value = documentation.values.get(attribute__uri=f'{BASE_URI}domain/{path}', **index)
            response = client.put(f'/api/v1/projects/projects/{documentation.pk}/values/{value.pk}/', {
                'attribute': Attribute.objects.get(uri=f'{BASE_URI}domain/{path}').pk,
                'set_prefix': value.set_prefix, 'set_index': value.set_index,
                'collection_index': value.collection_index, 'text': text, 'value_type': 'text',
                'external_id': external_id}, content_type='application/json')
            assert response.status_code == 200, response.content
            return response.json()
        return documentation, edit
    return open_project


def text(project, path, **index):
    return project.values.get(attribute__uri=f'{BASE_URI}domain/{path}', **index).text


def test_the_id_dropdown_offers_new_item(monkeypatch):
    monkeypatch.setattr(queries, '_cached_search', lambda *args: [])
    assert queries.query_sources('alpha', 'Q1') == [{'id': 'not found', 'text': 'new item'}]


def test_a_portal_page_switched_to_new_item_keeps_name_and_description(interview):
    '''The template of a new item: its page is not filled with the text "new item".'''
    model, edit = interview()
    save(model, answer('quantity', 'QQK1', set_index=0),
         answer('quantity/id', 'alpha (first) [mardi]', external_id='mardi:Q1', set_index=0),
         answer('quantity/name', 'alpha', set_prefix='0'),
         answer('quantity/description', 'first', set_prefix='0'))
    assert is_user_id(edit('quantity/id', 'new item', 'not found', set_index=0)['external_id'])
    assert (text(model, 'quantity/name'), text(model, 'quantity/description')) == ('alpha', 'first')


def test_an_own_publication_queries_no_citation(interview, monkeypatch):
    def query(*args):
        raise AssertionError('citation queried')
    monkeypatch.setattr('MaRDMO.publication.handlers._query_citations', query)
    model, edit = interview()
    save(model, answer('publication', 'P1', set_index=0),
         answer('publication/id', 'A paper (scientific article) [mardi]', external_id='mardi:Q1', set_index=0))
    assert is_user_id(edit('publication/id', 'new item', 'not found', set_index=0)['external_id'])
    assert not model.values.filter(attribute__uri=f'{BASE_URI}domain/publication/name', text='new item').exists()


def test_a_portal_item_gets_its_page_also_with_an_own_page_of_the_same_name(project):
    '''Pages are found by ID: the own "alpha (first)" is another item.'''
    model = project('mardmo-model-catalog')
    save(model, answer('quantity', 'QQK1', set_index=0),
         answer('quantity/id', 'new item', external_id='user:aaa', set_index=0),
         answer('quantity/name', 'alpha', set_prefix='0'),
         answer('quantity/description', 'first', set_prefix='0'))
    add_entities(model, f'{BASE_URI}domain/quantity', [Relatant.from_triple('mardi:Q1', 'alpha', 'first')],
                 'QQK')
    add_entities(model, f'{BASE_URI}domain/quantity', [Relatant.from_triple('mardi:Q1', 'alpha', 'first')],
                 'QQK')
    ids = model.values.filter(attribute__uri=f'{BASE_URI}domain/quantity/id').order_by('set_index')
    assert list(ids.values_list('external_id', flat=True)) == ['user:aaa', 'mardi:Q1']
