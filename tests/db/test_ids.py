'''Every item in a project has a real ID; "not found" becomes ``user:<uuid>`` (ids.py, router).'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

from MaRDMO import main
from MaRDMO.checks import Checks
from MaRDMO.checks.base import OLD_PROJECT
from MaRDMO.constants import BASE_URI
from MaRDMO.ids import id_attributes, is_user_id
from tests.db.conftest import answer, save

# Pages with an ID question, and items entered on a page without one of their own
PAGES = ['algorithm', 'benchmark', 'dataset', 'field', 'formulation', 'hardware', 'model',
         'problem', 'processstep', 'publication', 'quantity', 'software', 'task', 'workflow']
INLINE = ['hardware/cpu', 'processstep/instrument-relatant', 'processstep/method-relatant',
          'software/programming-language-relatant']


def saved(model, path, external_id, text='not found', **fields):
    '''Save an answer as an import does (``save()``, no request) and return it.'''
    value = answer(path, text, external_id=external_id, **fields)
    value.project = model
    value.save()
    return value


@pytest.fixture
def model(project):
    return project('mardmo-model-catalog')


def test_id_questions_are_the_pages_and_the_inline_items(db):
    assert id_attributes() == {f'{BASE_URI}domain/{path}' for path in [f'{page}/id' for page in PAGES] + INLINE}


@pytest.mark.parametrize('path', ['quantity/id', 'software/programming-language-relatant'])
def test_not_found_becomes_a_user_id(model, path):
    value = saved(model, path, 'not found', set_prefix='0')
    assert is_user_id(model.values.get(pk=value.pk).external_id)
    assert value.text == 'not found'


def test_two_new_items_get_different_ids(model):
    first = saved(model, 'quantity/id', 'not found', set_index=0)
    second = saved(model, 'quantity/id', 'not found', set_index=1)
    assert first.external_id != second.external_id


def test_selecting_not_found_again_keeps_the_id(model):
    value = saved(model, 'quantity/id', 'not found')
    user_id = value.external_id
    value.external_id = 'not found'
    value.save()
    assert model.values.get(pk=value.pk).external_id == user_id


def test_a_new_item_in_a_relation_gets_a_user_id(model):
    '''Its page gets the same ID (tests/db/test_relations.py).'''
    value = saved(model, 'formulation/element/quantity', 'not found', text='alpha (a quantity)', set_prefix='0')
    assert is_user_id(model.values.get(pk=value.pk).external_id)


def test_portal_ids_are_kept(model):
    value = saved(model, 'quantity/id', 'mardi:Q1', text='alpha (a quantity) [mardi]')
    assert model.values.get(pk=value.pk).external_id == 'mardi:Q1'


def test_answers_follow_the_item_when_its_id_changes(model):
    page = saved(model, 'quantity/id', 'not found')
    user_id = page.external_id
    save(model, answer('formulation/element/quantity', 'alpha (a quantity)', external_id=user_id, set_prefix='0'))
    relation = model.values.get(external_id=user_id, attribute__uri__endswith='element/quantity')
    updated = relation.updated

    page.external_id, page.text = 'mardi:Q1', 'alpha (a quantity) [mardi]'
    page.save()

    relation.refresh_from_db()
    assert relation.external_id == 'mardi:Q1'
    # Not saved: an interview open with the relation can still save it
    assert relation.updated == updated


def test_a_portal_item_used_as_template_keeps_its_references(model):
    '''The page becomes a new item ("not found"); the model may still contain the old one.'''
    page = saved(model, 'formulation/id', 'mardi:Q1', text='old formula (a formula) [mardi]')
    save(model, answer('model/formulation-relatant', 'old formula (a formula) [mardi]', external_id='mardi:Q1',
                       set_prefix='0'))

    page.external_id = 'not found'
    page.save()

    assert is_user_id(model.values.get(pk=page.pk).external_id)
    assert model.values.get(attribute__uri__endswith='model/formulation-relatant').external_id == 'mardi:Q1'


def test_answers_stay_with_the_item_on_another_page(model):
    '''Two pages of the same portal item: changing one does not take the references.'''
    first = saved(model, 'quantity/id', 'mardi:Q1', text='alpha [mardi]', set_index=0)
    saved(model, 'quantity/id', 'mardi:Q1', text='alpha [mardi]', set_index=1)
    save(model, answer('formulation/element/quantity', 'alpha [mardi]', external_id='mardi:Q1', set_prefix='0'))

    first.external_id = 'mardi:Q2'
    first.save()

    assert model.values.filter(external_id='mardi:Q1').count() == 2


def test_the_interview_gets_the_user_id_back(model, client, django_user_model):
    '''The interview shows what the backend returns, so the field holds the real ID at once.'''
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=model, user=user, role='owner')
    client.force_login(user)
    attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/quantity/id')
    response = client.post(f'/api/v1/projects/projects/{model.pk}/values/', {
        'attribute': attribute.pk, 'set_prefix': '', 'set_index': 0, 'collection_index': 0,
        'text': 'not found', 'external_id': 'not found', 'value_type': 'text'}, content_type='application/json')
    assert response.status_code == 201
    assert is_user_id(response.json()['external_id'])


def test_a_project_made_before_0_8_0_is_reported(model, monkeypatch):
    '''Its items have "not found" as ID (saved before 0.8.0, so not converted); the export stops.'''
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    save(model, answer('quantity', 'Quantity 1', set_index=0),
         answer('quantity/id', 'not found', external_id='not found', set_index=0),
         answer('quantity/name', 'alpha', set_prefix='0'),
         answer('quantity/description', 'a quantity', set_prefix='0'))
    assert any(OLD_PROJECT in message for message in check_messages(model))


def test_a_project_of_0_8_0_is_not_reported(model, monkeypatch):
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    save(model, answer('quantity', 'Quantity 1', set_index=0),
         answer('quantity/id', 'not found', external_id='user:alpha', set_index=0),
         answer('quantity/name', 'alpha', set_prefix='0'),
         answer('quantity/description', 'a quantity', set_prefix='0'))
    assert not any(OLD_PROJECT in message for message in check_messages(model))


def check_messages(project):
    '''The messages of the checks the export runs first.'''
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, _ = provider.get_post_data()
    return [str(message) for message in Checks().run_model(project=project, data=answers, catalog=str(project.catalog))]
