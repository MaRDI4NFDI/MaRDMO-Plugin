'''Relations show the current name and description of their item's page (#101).'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

from MaRDMO.constants import BASE_URI
from tests.db.conftest import answer, save


@pytest.fixture
def interview(project, client, django_user_model):
    '''A model project with a quantity page (own or portal) and a task relating to it; *edit* saves as the interview.'''
    user = django_user_model.objects.create_user('owner', password='owner')
    client.force_login(user)

    def open_project(identifier='user:aaa', title='alpha (first)'):
        model = project('mardmo-model-catalog')
        Membership.objects.create(project=model, user=user, role='owner')
        save(model, answer('quantity', 'QQK1', set_index=0),
             answer('quantity/id', 'not found' if identifier.startswith('user:') else f'{title} [mardi]',
                    external_id=identifier, set_index=0),
             answer('quantity/name', 'alpha', set_prefix='0'),
             answer('quantity/description', 'first', set_prefix='0'),
             answer('task/quantity-relatant', title, external_id=identifier, set_prefix='0'))

        def edit(path, text, **index):
            value = model.values.get(attribute__uri=f'{BASE_URI}domain/{path}', **index)
            response = client.put(f'/api/v1/projects/projects/{model.pk}/values/{value.pk}/', {
                'attribute': Attribute.objects.get(uri=f'{BASE_URI}domain/{path}').pk,
                'set_prefix': value.set_prefix, 'set_index': value.set_index,
                'collection_index': value.collection_index, 'text': text, 'value_type': 'text',
                'external_id': value.external_id}, content_type='application/json')
            assert response.status_code == 200, response.content
        return model, edit
    return open_project


def text(model, path):
    return model.values.get(attribute__uri=f'{BASE_URI}domain/{path}').text


def test_relations_get_the_new_name(interview):
    model, edit = interview()
    edit('quantity/name', 'reaction rate', set_prefix='0')
    assert text(model, 'task/quantity-relatant') == 'reaction rate (first)'


def test_relations_get_the_new_description(interview):
    model, edit = interview()
    edit('quantity/description', 'rate of a reaction', set_prefix='0')
    assert text(model, 'task/quantity-relatant') == 'alpha (rate of a reaction)'


def test_a_cleared_description_leaves_the_label(interview):
    model, edit = interview()
    edit('quantity/description', '', set_prefix='0')
    assert text(model, 'task/quantity-relatant') == 'alpha'


def test_a_portal_item_keeps_its_tag(interview):
    model, edit = interview('mardi:Q1', 'alpha (first) [mardi]')
    edit('quantity/name', 'Alpha', set_prefix='0')
    assert text(model, 'task/quantity-relatant') == 'Alpha (first) [mardi]'


def test_the_pages_own_id_keeps_its_text(interview):
    '''For an own item it says "not found" until the ID dropdown shows labels (#119).'''
    model, edit = interview()
    edit('quantity/name', 'reaction rate', set_prefix='0')
    assert text(model, 'quantity/id') == 'not found'


def test_a_cleared_name_changes_nothing(interview):
    model, edit = interview()
    edit('quantity/name', '', set_prefix='0')
    assert text(model, 'task/quantity-relatant') == 'alpha (first)'


def test_the_relation_keeps_its_time_so_an_open_interview_can_save_it(interview):
    model, edit = interview()
    before = model.values.get(attribute__uri=f'{BASE_URI}domain/task/quantity-relatant').updated
    edit('quantity/name', 'reaction rate', set_prefix='0')
    assert model.values.get(attribute__uri=f'{BASE_URI}domain/task/quantity-relatant').updated == before


def test_another_project_is_not_touched(interview):
    model, edit = interview()
    other, _ = interview()
    edit('quantity/name', 'reaction rate', set_prefix='0')
    assert text(other, 'task/quantity-relatant') == 'alpha (first)'


def test_a_publication_on_its_own_tab(interview):
    '''A publication's name is an answer of its tab (set index), not of a set prefix.

    No question refers to publications yet; any answer with its ID is synced.
    '''
    model, edit = interview()
    save(model, answer('publication', 'P1', set_index=0),
         answer('publication/id', 'not found', external_id='user:paper', set_index=0),
         answer('publication/name', 'A paper', set_index=0),
         answer('publication/description', 'scientific article', set_index=0),
         answer('task/quantity-relatant', 'A paper (scientific article)', external_id='user:paper',
                set_prefix='1'))
    edit('publication/name', 'The paper', set_index=0, set_prefix='')
    assert model.values.get(external_id='user:paper', set_prefix='1').text == 'The paper (scientific article)'
