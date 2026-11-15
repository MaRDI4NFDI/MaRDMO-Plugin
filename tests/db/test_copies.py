'''A copied tab is the same item as its original until the user decides (#117).

RDMO copies a tab with ``bulk_create``, so MaRDMO does not change it: the
copy keeps the ID, and checks and preview report both pages as one item.
'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

from MaRDMO import main
from MaRDMO.checks import Checks
from MaRDMO.constants import BASE_URI, CATALOG_MODEL
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


def test_a_copied_tab_keeps_the_id(model, client):
    copy_tab(model, client)
    ids = model.values.filter(attribute__uri=f'{BASE_URI}domain/quantity/id').order_by('set_index')
    assert list(ids.values_list('external_id', flat=True)) == ['user:aaa', 'user:aaa']


def test_a_copied_tab_is_reported_as_the_same_item(model, client):
    copy_tab(model, client)
    answers = answers_of(model)
    messages = [str(m) for m in Checks().run_model(project=model, data=answers, catalog=str(model.catalog))]
    assert any('QQK2' in m and 'Same Item as Page QQK1' in m for m in messages)


def test_relations_find_the_copy_when_the_original_is_deleted(model, client):
    '''The copy has the item's ID: deleting either page leaves relations with a page.'''
    copy_tab(model, client)
    original = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity', set_index=0)
    response = client.delete(f'/api/v1/projects/projects/{model.pk}/values/{original.pk}/set/')
    assert response.status_code == 204
    answers = answers_of(model)
    messages = [str(m) for m in Checks().run_model(project=model, data=answers, catalog=str(model.catalog))]
    assert not any('not found in' in m or 'Same Item' in m for m in messages)


def test_the_first_of_two_pages_with_one_id_is_the_item():
    answers = {'quantity': {index: {**entry, 'Tab': f'QQK{index + 1}'} for index, entry in enumerate([
        {'ID': 'mardi:Q1', 'Name': 'a'}, {'ID': 'mardi:Q1', 'Name': 'a'},
        {'ID': 'user:1', 'Name': 'b', 'Description': 'c'}, {'ID': 'user:1', 'Name': 'b', 'Description': 'c'}])}}
    checks = Checks()
    checks.id_name_description(None, answers, CATALOG_MODEL)
    same = {problem.page.tab: problem.message for problem in checks.err if 'Same' in problem.message}
    assert same == {'QQK2': 'Same Item as Page QQK1 (delete one of them)',
                    'QQK4': 'Same Item as Page QQK3 (delete one of them)'}
