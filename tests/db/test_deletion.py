'''Deleting an item page removes the answers that refer to its item (#102).'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

from MaRDMO.constants import BASE_URI
from MaRDMO.ids import relation_rows
from tests.db.conftest import answer, save


@pytest.fixture
def owner(client, django_user_model):
    user = django_user_model.objects.create_user('owner', password='owner')
    client.force_login(user)
    return user


def documentation(project, owner, catalog='mardmo-model-catalog'):
    created = project(catalog)
    Membership.objects.create(project=created, user=owner, role='owner')
    return created


def page(section, index, identifier, name):
    return [answer(section, f'{section} {index + 1}', set_index=index),
            answer(f'{section}/id', 'not found', external_id=identifier, set_index=index),
            answer(f'{section}/name', name, set_prefix=str(index)),
            answer(f'{section}/description', f'a {name}', set_prefix=str(index))]


def delete_tab(client, project, section, index):
    '''"Delete tab" of the interview: RDMO's set deletion with the tab's set answer.'''
    tab = project.values.get(attribute__uri=f'{BASE_URI}domain/{section}', set_index=index)
    response = client.delete(f'/api/v1/projects/projects/{project.pk}/values/{tab.pk}/set/')
    assert response.status_code == 204, response.content


def answers(project, path):
    return sorted(project.values.filter(attribute__uri=f'{BASE_URI}domain/{path}').values_list(
        'set_prefix', 'set_index', 'collection_index', 'external_id', 'text'))


@pytest.fixture
def model(project, owner):
    '''Two quantities; a task relates to both (row 0) and to the first only (row 1).'''
    model = documentation(project, owner)
    save(model, *page('quantity', 0, 'user:aaa', 'alpha'), *page('quantity', 1, 'user:bbb', 'beta'),
         *page('task', 0, 'user:task', 'a task'),
         answer('task/quantity-relation', 'contains', set_prefix='0', set_index=0),
         answer('task/quantity-relatant', 'alpha (a alpha)', external_id='user:aaa', set_prefix='0', set_index=0),
         answer('task/quantity-relatant', 'beta (a beta)', external_id='user:bbb', set_prefix='0', set_index=0,
                collection_index=1),
         answer('task/quantity-relation', 'contains', set_prefix='0', set_index=1),
         answer('task/quantity-relatant', 'alpha (a alpha)', external_id='user:aaa', set_prefix='0', set_index=1))
    return model


def test_deleting_a_page_removes_the_relations_to_its_item(model, client):
    delete_tab(client, model, 'quantity', 0)
    assert answers(model, 'task/quantity-relatant') == [('0', 0, 1, 'user:bbb', 'beta (a beta)')]


def test_a_row_without_target_loses_its_relation_type(model, client):
    '''Row 0 still relates to beta; row 1 related only to alpha.'''
    delete_tab(client, model, 'quantity', 0)
    assert answers(model, 'task/quantity-relation') == [('0', 0, 0, '', 'contains')]


def test_clearing_the_id_of_a_page_removes_nothing(model, client):
    '''The user may select another item next; only a deleted tab takes its relations along.'''
    identifier = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity/id', set_index=0)
    response = client.delete(f'/api/v1/projects/projects/{model.pk}/values/{identifier.pk}/')
    assert response.status_code == 204
    assert len(answers(model, 'task/quantity-relatant')) == 3


def test_relations_stay_with_another_page_of_the_item(model, client):
    '''A copied tab has the item's ID (#117).'''
    save(model, *page('quantity', 2, 'user:aaa', 'alpha'))
    delete_tab(client, model, 'quantity', 0)
    assert len(answers(model, 'task/quantity-relatant')) == 3


def test_a_specialization_loses_its_assumptions_with_its_last_target(project, owner, client):
    model = documentation(project, owner)
    save(model, *page('model', 0, 'user:general', 'general model'), *page('model', 1, 'user:special', 'special'),
         *page('formulation', 0, 'user:f', 'assumption'),
         answer('model/model-relation', 'specialized by', set_prefix='0', set_index=0),
         answer('model/model-relatant', 'special (a special)', external_id='user:special', set_prefix='0'),
         answer('model/model-assumption', 'assumption (a assumption)', external_id='user:f', set_prefix='0'))
    delete_tab(client, model, 'model', 1)
    assert answers(model, 'model/model-relation') == answers(model, 'model/model-assumption') == []


def test_a_deleted_assumption_leaves_its_specialization(project, owner, client):
    model = documentation(project, owner)
    save(model, *page('model', 0, 'user:general', 'general model'), *page('model', 1, 'user:special', 'special'),
         *page('formulation', 0, 'user:f', 'assumption'),
         answer('model/model-relation', 'specialized by', set_prefix='0', set_index=0),
         answer('model/model-relatant', 'special (a special)', external_id='user:special', set_prefix='0'),
         answer('model/model-assumption', 'assumption (a assumption)', external_id='user:f', set_prefix='0'))
    delete_tab(client, model, 'formulation', 0)
    assert answers(model, 'model/model-assumption') == []
    assert len(answers(model, 'model/model-relatant')) == len(answers(model, 'model/model-relation')) == 1


def test_a_usage_of_a_process_step_keeps_its_software(project, owner, client):
    '''A usage is no relation row: the user chooses another algorithm, the checks report the missing one.'''
    workflow = documentation(project, owner, 'mardmo-interdisciplinary-workflow-catalog')
    save(workflow, *page('algorithm', 0, 'user:alg', 'solver'), *page('software', 0, 'user:sw', 'code'),
         *page('processstep', 0, 'user:ps', 'step'),
         answer('processstep/algorithm-relatant', 'solver (a solver)', external_id='user:alg', set_prefix='0'),
         answer('processstep/software-relatant', 'code (a code)', external_id='user:sw', set_prefix='0'))
    delete_tab(client, workflow, 'algorithm', 0)
    assert answers(workflow, 'processstep/algorithm-relatant') == []
    assert len(answers(workflow, 'processstep/software-relatant')) == 1


def test_publication_relations_to_the_item_are_removed(model, client):
    save(model, *page('publication', 0, 'user:paper', 'paper'),
         answer('publication/entity-relation', 'documents', set_prefix='0', set_index=0),
         answer('publication/entity-relatant', 'alpha (a alpha)', external_id='user:aaa', set_prefix='0'))
    delete_tab(client, model, 'quantity', 0)
    assert answers(model, 'publication/entity-relatant') == answers(model, 'publication/entity-relation') == []


def test_every_relation_type_belongs_to_a_row(db, questionnaire):
    '''A relation type question outside a row would stay without target.'''
    relation_types = {f'{BASE_URI}domain/{uri}' for uri in (
        uri[len(f'{BASE_URI}domain/'):] for uri in questionnaire['attribute'])
        if 'relation' in uri.rsplit('/', 1)[-1] and 'relatant' not in uri.rsplit('/', 1)[-1]}
    rows = {uri for _, others in relation_rows().values() for uri in others}
    assert relation_types and sorted(relation_types - rows) == []
    assert all(Attribute.objects.filter(uri=uri).exists() for uri in relation_rows())
