'''What MaRDMO does when answers are saved or deleted (router).'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

from MaRDMO.constants import BASE_URI
from tests.db.conftest import answer, save


@pytest.fixture
def owner(project, client, django_user_model):
    '''A model project and a test client logged in as its owner.'''
    model = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=model, user=user, role='owner')
    client.force_login(user)
    return model, client


def save_in_interview(model, client, path, text):
    '''Save an answer as the interview does: through RDMO's project value API.'''
    attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/{path}')
    return client.post(f'/api/v1/projects/projects/{model.pk}/values/', {
        'attribute': attribute.pk, 'set_prefix': '0', 'set_index': 0, 'collection_index': 0,
        'text': text, 'value_type': 'text'}, content_type='application/json')


def test_interview_rejects_a_line_break_in_a_single_line_answer(owner):
    model, client = owner
    response = save_in_interview(model, client, 'quantity/long-description', 'first\nsecond')
    assert response.status_code == 400
    assert not model.values.exists()


def test_interview_accepts_a_valid_answer(owner):
    model, client = owner
    response = save_in_interview(model, client, 'quantity/long-description', 'one line')
    assert response.status_code == 201
    assert model.values.get().text == 'one line'


def test_saves_outside_the_interview_are_not_validated(project):
    '''A project import must not fail on answers that newer rules reject; the checks report them.'''
    model = project('mardmo-model-catalog')
    value = answer('quantity/long-description', 'first\nsecond', set_prefix='0')
    value.project = model
    value.save()
    assert model.values.get().text == 'first\nsecond'


def test_deleting_a_publication_removes_its_citation_data_only(project):
    '''Publication 1 is deleted; publications 0 and 10 keep their data (10 is not "1…").'''
    model = project('mardmo-model-catalog')
    for index in (0, 1, 10):
        save(model, answer('publication', f'P{index}', set_index=index),
             answer('publication/name', f'paper {index}', set_index=index),
             answer('publication/title', f'title {index}', set_index=index))
    model.values.get(attribute__uri=f'{BASE_URI}domain/publication', set_index=1).delete()
    names = model.values.filter(attribute__uri=f'{BASE_URI}domain/publication/name')
    assert sorted(names.values_list('text', flat=True)) == ['paper 0', 'paper 10']
    assert not model.values.filter(set_index=1).exists()
