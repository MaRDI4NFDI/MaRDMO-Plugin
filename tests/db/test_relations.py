'''Relations hold the ID of the item they refer to; "new" creates its page with that ID (#100).'''
import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership

from MaRDMO.checks import Checks
from MaRDMO.checks.base import OLD_PROJECT
from MaRDMO.constants import BASE_URI
from MaRDMO.ids import is_user_id
from MaRDMO.providers import MaRDMOProvider
import MaRDMO.queries as queries
from tests.db.conftest import answer, save


@pytest.fixture
def interview(project, client, django_user_model):
    '''Save answers of a project of *catalog* as the interview does: through RDMO's project value API.'''
    user = django_user_model.objects.create_user('owner', password='owner')
    client.force_login(user)

    def open_project(catalog='mardmo-model-catalog'):
        documentation = project(catalog)
        Membership.objects.create(project=documentation, user=user, role='owner')

        def post(path, text, external_id='', set_prefix='0', set_index=0, collection_index=0):
            response = client.post(f'/api/v1/projects/projects/{documentation.pk}/values/', {
                'attribute': Attribute.objects.get(uri=f'{BASE_URI}domain/{path}').pk,
                'set_prefix': set_prefix, 'set_index': set_index, 'collection_index': collection_index,
                'text': text, 'external_id': external_id, 'value_type': 'text'}, content_type='application/json')
            return response
        return documentation, post
    return open_project


def page(project, section, external_id):
    '''Name and description of the page of *section* with the ID *external_id* (``None``: no page).'''
    ids = project.values.filter(attribute__uri=f'{BASE_URI}domain/{section}/id', external_id=external_id)
    if not ids.exists():
        return None
    index = str(ids.get().set_index)
    texts = {value.attribute.uri.rsplit('/', 1)[1]: value.text for value in project.values.filter(
        attribute__uri__in=[f'{BASE_URI}domain/{section}/name', f'{BASE_URI}domain/{section}/description'],
        set_prefix=index)}
    return texts.get('name'), texts.get('description')


def pages(project, section):
    return project.values.filter(attribute__uri=f'{BASE_URI}domain/{section}/id').count()


def test_new_item_in_a_relation_gets_a_page_with_its_id(interview):
    model, post = interview()
    response = post('model/problem-relatant', 'reaction rate', 'not found')
    assert response.status_code == 201
    user_id = response.json()['external_id']
    assert is_user_id(user_id)
    assert page(model, 'problem', user_id) == ('reaction rate', '')


def test_new_item_typed_with_description(interview):
    model, post = interview()
    user_id = post('model/problem-relatant', 'reaction rate (rate of a reaction)', 'not found').json()['external_id']
    assert page(model, 'problem', user_id) == ('reaction rate', 'rate of a reaction')


def test_new_again_is_another_item(interview):
    '''"new" always creates a page, also with the label of an own item (another item may share it).'''
    model, post = interview()
    first = post('model/problem-relatant', 'reaction rate', 'not found', collection_index=0).json()['external_id']
    second = post('model/problem-relatant', 'reaction rate', 'not found', collection_index=1).json()['external_id']
    assert first != second
    assert pages(model, 'problem') == 2


def test_own_item_selected_again_is_the_same_item(interview):
    model, post = interview()
    user_id = post('model/problem-relatant', 'reaction rate', 'not found', collection_index=0).json()['external_id']
    response = post('model/problem-relatant', 'reaction rate ()', user_id, collection_index=1)
    assert response.json()['external_id'] == user_id
    assert pages(model, 'problem') == 1


def test_a_relation_changed_to_another_item_moves_nothing(interview):
    model, post = interview()
    first = post('model/problem-relatant', 'first', 'not found', collection_index=0).json()['external_id']
    relation = post('model/problem-relatant', 'first ()', first, collection_index=1)
    second = post('model/problem-relatant', 'second', 'not found', collection_index=2).json()['external_id']

    value = model.values.get(pk=relation.json()['id'])
    value.external_id, value.text = second, 'second ()'
    value.save()

    assert model.values.filter(external_id=first).count() == 2   # its page and the first relation


def test_a_portal_item_needs_a_description(interview):
    _, post = interview()
    assert post('model/problem-relatant', 'reaction rate', 'mardi:Q1').status_code == 400


def test_unclosed_parenthesis_is_rejected(interview):
    _, post = interview()
    assert post('model/problem-relatant', 'reaction rate (rate', 'not found').status_code == 400


def test_new_item_without_page_in_the_workflow_catalog(interview, monkeypatch):
    '''The workflow catalog has no section for research fields: the field stays on the process step.'''
    workflow, post = interview('mardmo-interdisciplinary-workflow-catalog')
    response = post('processstep/field-relatant', 'fluid dynamics (study of fluid flow)', 'not found')
    assert is_user_id(response.json()['external_id'])
    assert pages(workflow, 'field') == 0


def test_dropdown_offers_own_items_with_the_id_of_their_page(project, monkeypatch):
    monkeypatch.setattr(queries, 'query_sources', lambda **kwargs: [])
    model = project('mardmo-model-catalog')
    save(model, answer('problem/id', 'not found', external_id='user:1', set_index=0),
         answer('problem/name', 'reaction rate', set_prefix='0'),
         answer('problem/description', 'rate of a reaction', set_prefix='0'))
    provider = MaRDMOProvider('RelatedResearchProblemWithCreation', '', 'MaRDMO.providers.MaRDMOProvider')
    options = provider.get_options(model, search='reaction')
    assert {'id': 'user:1', 'text': 'reaction rate (rate of a reaction)'} in options


def test_relation_without_id_is_reported_as_made_before_0_8_0(project, monkeypatch):
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    model = project('mardmo-model-catalog')
    save(model, answer('model', 'Model 1', set_index=0),
         answer('model/id', 'not found', external_id='user:m', set_index=0),
         answer('model/name', 'a model', set_prefix='0'),
         answer('model/description', 'a model', set_prefix='0'),
         answer('model/problem-relatant', 'reaction rate (rate of a reaction)', external_id='not found',
                set_prefix='0'))
    assert any(OLD_PROJECT in message for message in check_messages(model))


def check_messages(project):
    from MaRDMO import main
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, _ = provider.get_post_data()
    return [str(message) for message in Checks().run_model(project=project, data=answers,
                                                           catalog=str(project.catalog))]


def test_relations_show_the_current_name_of_their_page():
    '''Name and description come from the page with the relation's ID, not from the text it was saved with.'''
    from MaRDMO.helpers import link_to_pages
    answers = {'problem': {0: {'ID': 'user:1', 'Name': 'reaction rate', 'Description': 'rate of a reaction'}},
               'model': {0: {'ID': 'user:m', 'Name': 'a model', 'Description': 'a model',
                             'RPRelatant': {0: {'ID': 'user:1', 'Name': 'old name', 'Description': ''}}}}}
    link_to_pages(answers)
    assert answers['model'][0]['RPRelatant'][0] == {
        'ID': 'user:1', 'Name': 'reaction rate', 'Description': 'rate of a reaction'}


def test_formula_elements_are_linked_to_the_quantity_with_their_id():
    '''Two quantities with the same name (#123): each element gets its own.'''
    from MaRDMO.model.utils import map_entity_quantity
    answers = {
        'quantity': {0: {'ID': 'user:a', 'Name': 'concentration', 'Description': 'of A', 'QorQK': 'Quantity'},
                     1: {'ID': 'user:b', 'Name': 'concentration', 'Description': 'of B', 'QorQK': 'Quantity'}},
        'formulation': {0: {'element': {0: {'quantity': {'ID': 'user:a'}}, 1: {'quantity': {'ID': 'user:b'}},
                                        2: {'quantity': {'ID': 'mardi:Q9', 'Name': 'concentration'}}}}}}
    map_entity_quantity(answers, 'formulation')
    elements = answers['formulation'][0]['element']
    assert elements[0]['Info']['Description'] == 'of A'
    assert elements[1]['Info']['Description'] == 'of B'
    assert 'Info' not in elements[2]


def test_two_own_pages_with_the_same_name_and_description_are_reported(project, monkeypatch):
    '''The export would make one item of them.'''
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    model = project('mardmo-model-catalog')
    for index in (0, 1):
        save(model, answer('problem', f'RP{index + 1}', set_index=index),
             answer('problem/id', 'not found', external_id=f'user:{index}', set_index=index),
             answer('problem/name', 'reaction rate', set_prefix=str(index)),
             answer('problem/description', 'rate of a reaction', set_prefix=str(index)))
    assert any('Same Name and Short Description as Page RP1' in message for message in check_messages(model))


def test_new_field_of_a_process_step_is_not_an_old_project(interview):
    '''A field entered on a process step (no field section in the workflow catalog) has a user: ID.'''
    from MaRDMO import main
    workflow, post = interview('mardmo-interdisciplinary-workflow-catalog')
    post('processstep', 'PS1', set_prefix='', set_index=0)
    post('processstep/field-relatant', 'fluid dynamics (study of fluid flow)', 'not found')
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = workflow, None
    answers, _ = provider.get_post_data()
    messages = [str(m) for m in Checks().run_workflow(project=workflow, data=answers, catalog=str(workflow.catalog))]
    assert not any(OLD_PROJECT in message for message in messages)
