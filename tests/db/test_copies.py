'''A copied tab is a new item; a copy of a portal item shows that item (#117, #186).

RDMO copies a tab with ``bulk_create``, without signals, so the copy has the
ID of its original; at the end of the copy request MaRDMO gives a copy of
an own item an ID of its own, and the links stay with the original.  A copy
of a MaRDI Portal or Wikidata item keeps its ID: both tabs are that item,
which the checks report until the user decides.
'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

from MaRDMO import main
from MaRDMO.model.checks import ModelChecks
from MaRDMO.constants import BASE_URI
from MaRDMO.model.catalog import CATALOG_MODEL
from tests.db.conftest import answer, save


@pytest.fixture
def model(project, client, django_user_model, monkeypatch):
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    client.force_login(user)
    save(documentation, answer('quantity', 'QQK1', set_index=0),
         answer('quantity/id', 'not found', external_id='user:aaa', set_index=0),
         answer('quantity/name', 'reaction rate', set_prefix='0'),
         answer('quantity/description', 'rate of a reaction', set_prefix='0'),
         answer('task', 'CT1', set_index=0),
         answer('task/id', 'not found', external_id='user:task', set_index=0),
         answer('task/name', 'a task', set_prefix='0'),
         answer('task/description', 'a computational task', set_prefix='0'),
         answer('task/quantity-relatant', 'reaction rate (rate of a reaction)', external_id='user:aaa',
                set_prefix='0|0'))
    return documentation


def copy_tab(model, client):
    '''"Copy tab" of the interview: RDMO's copy endpoint with a new set value.'''
    original = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity', set_index=0)
    response = client.post(f'/api/v1/projects/projects/{model.pk}/values/set/', {
        'copy_set_value': original.pk,
        'attribute': Attribute.objects.get(uri=f'{BASE_URI}domain/quantity').pk,
        'set_prefix': '', 'set_index': 1, 'collection_index': 0, 'text': 'QQK2', 'value_type': 'text',
    }, content_type='application/json')
    assert response.status_code == 201, response.content


def answers_of(project):
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    return provider.get_post_data()[0]


def ids_of(model, section='quantity'):
    return list(model.values.filter(attribute__uri=f'{BASE_URI}domain/{section}/id', set_prefix='')
                .order_by('set_index').values_list('external_id', flat=True))


def relation(model):
    return model.values.get(attribute__uri=f'{BASE_URI}domain/task/quantity-relatant').external_id


def messages_of(model):
    answers = answers_of(model)
    return [str(m) for m in ModelChecks().run(project=model, data=answers, catalog=str(model.catalog))]


def test_a_copy_of_an_own_item_gets_an_id_of_its_own(model, client):
    copy_tab(model, client)
    original, copy = ids_of(model)
    assert original == 'user:aaa' and copy.startswith('user:') and copy != original
    # The links stay with the original
    assert relation(model) == 'user:aaa'


def test_a_copy_with_its_name_unchanged_is_reported(model, client):
    copy_tab(model, client)
    assert any('QQK2' in m and 'Same Name and Short Description as Page QQK1' in m for m in messages_of(model))


def test_deleting_the_original_of_an_own_copy_removes_its_links(model, client):
    '''The links were the original's; the copy is another item.'''
    copy_tab(model, client)
    original = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity', set_index=0)
    assert client.delete(f'/api/v1/projects/projects/{model.pk}/values/{original.pk}/set/').status_code == 204
    assert not model.values.filter(attribute__uri=f'{BASE_URI}domain/task/quantity-relatant').exists()


@pytest.fixture
def portal_original(model):
    model.values.filter(attribute__uri=f'{BASE_URI}domain/quantity/id').update(
        external_id='mardi:Q5', text='reaction rate (rate of a reaction)')
    model.values.filter(attribute__uri=f'{BASE_URI}domain/task/quantity-relatant').update(external_id='mardi:Q5')
    return model


def test_a_copy_of_a_portal_item_keeps_its_id_and_is_reported(portal_original, client):
    copy_tab(portal_original, client)
    assert ids_of(portal_original) == ['mardi:Q5', 'mardi:Q5']
    assert any('QQK2' in m and 'Same Item as Page QQK1' in m for m in messages_of(portal_original))


def test_deleting_the_original_of_a_portal_copy_leaves_the_links_with_the_copy(portal_original, client):
    copy_tab(portal_original, client)
    original = portal_original.values.get(attribute__uri=f'{BASE_URI}domain/quantity', set_index=0)
    assert client.delete(f'/api/v1/projects/projects/{portal_original.pk}/values/{original.pk}/set/').status_code == 204
    assert relation(portal_original) == 'mardi:Q5'
    assert not any('not found in' in m or 'Same Item' in m for m in messages_of(portal_original))


def test_the_interview_sending_the_copy_s_old_id_again_changes_nothing(model, client):
    copy_tab(model, client)
    copy = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity/id', set_index=1)
    own = copy.external_id
    response = client.put(f'/api/v1/projects/projects/{model.pk}/values/{copy.pk}/', {
        'attribute': copy.attribute_id, 'set_prefix': '', 'set_index': 1, 'collection_index': 0,
        'text': 'new item', 'external_id': 'user:aaa', 'value_type': 'text'}, content_type='application/json')
    assert response.status_code == 200 and response.json()['external_id'] == own
    assert relation(model) == 'user:aaa'


def test_a_tab_taken_over_twice_from_another_project_gives_two_items(model, client, project):
    '''"Import" of the interview: RDMO's copy endpoint with the ID of the tab to fill.'''
    other = project('mardmo-model-catalog')
    Membership.objects.create(project=other, user=model.memberships.first().user, role='owner')
    save(other, answer('quantity', 'X', set_index=0),
         answer('quantity/id', 'not found', external_id='user:energy', set_index=0),
         answer('quantity/name', 'energy', set_prefix='0'))
    source = other.values.get(attribute__uri=f'{BASE_URI}domain/quantity', set_index=0)
    for index in (1, 2):
        save(model, answer('quantity', f'QQK{index + 1}', set_index=index))
        target = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity', set_index=index)
        response = client.post(f'/api/v1/projects/projects/{model.pk}/values/set/', {
            'id': target.pk, 'attribute': target.attribute_id, 'set_prefix': '', 'set_index': index,
            'text': target.text, 'copy_set_value': source.pk}, content_type='application/json')
        assert response.status_code == 201, response.content
    first, second = ids_of(model)[1:]
    assert first == 'user:energy' and second.startswith('user:') and second != first


def test_the_first_of_two_pages_with_one_id_is_the_item():
    answers = {'quantity': {index: {**entry, 'Tab': f'QQK{index + 1}'} for index, entry in enumerate([
        {'ID': 'mardi:Q1', 'Name': 'a'}, {'ID': 'mardi:Q1', 'Name': 'a'},
        {'ID': 'user:1', 'Name': 'b', 'Description': 'c'}, {'ID': 'user:1', 'Name': 'b', 'Description': 'c'}])}}
    checks = ModelChecks()
    checks.id_name_description(None, answers, CATALOG_MODEL)
    same = {problem.page.tab: problem.message for problem in checks.err if 'Same' in problem.message}
    assert same == {'QQK2': 'Same Item as Page QQK1 (delete one of them)',
                    'QQK4': 'Same Item as Page QQK3 (delete one of them)'}
