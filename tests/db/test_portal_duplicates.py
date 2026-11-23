'''The preview's items already on the MaRDI Portal (in "Before you export") and their reuse (#141).

The portal's answers are faked: find_portal_items finds what a test gives it.
'''
import pytest
from django.test import Client
from rdmo.projects.models import Membership

from MaRDMO.core.constants import BASE_URI
from MaRDMO.core.config import get_items
from MaRDMO.sources.portal import PortalItems
from tests.db.conftest import answer, save
from tests.support.html import attribute, element, elements, export_button, links, preview_page, text

ITEMS = get_items()


def markers(*classes):
    return {'class': set(classes), 'community': set(), 'profile': set()}


@pytest.fixture
def model(project, client, django_user_model, monkeypatch):
    '''A quantity (used by a task), the task, and a research field from Wikidata.'''
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    client.force_login(user)
    save(documentation,
         answer('quantity', 'QQK1', set_index=0),
         answer('quantity/id', 'new item', external_id='user:mass', set_index=0),
         answer('quantity/name', 'mass', set_prefix='0'),
         answer('quantity/description', 'physical quantity', set_prefix='0'),
         answer('task', 'CT1', set_index=0),
         answer('task/id', 'new item', external_id='user:task', set_index=0),
         answer('task/name', 'weighing', set_prefix='0'),
         answer('task/description', 'measure a mass', set_prefix='0'),
         answer('task/quantity-relatant', 'mass (physical quantity)', external_id='user:mass', set_prefix='0|0'),
         answer('field', 'AD1', set_index=0),
         answer('field/id', 'ecology (study)', external_id='wikidata:Q7150', set_index=0),
         answer('field/name', 'ecology', set_prefix='0'),
         answer('field/description', 'study', set_prefix='0'))
    return documentation


@pytest.fixture
def portal(monkeypatch):
    '''The portal has what a test puts into it: ``portal(by_label=..., by_wikidata=..., markers=...)``.'''
    def use(**found):
        monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: PortalItems(**found))
        monkeypatch.setattr('MaRDMO.duplicates.portal_labels',
                            lambda qids, waits=(), deadline=None: {qid: ('ecology', 'branch of biology') for qid in qids})
    return use


def test_without_duplicates_the_preview_has_no_section(model, client, portal):
    '''The documentation is incomplete, so the button is disabled for that reason, not for duplicates.'''
    portal()
    html = preview_page(client, model)
    assert not elements(html, id='portal-duplicates') and elements(html, id='export-problems')
    assert 'Decide on the items' not in text(element(html, id='export-blocked'))


def test_a_failed_lookup_asks_to_try_again(model, client, portal):
    portal(label_failed=True)
    html = preview_page(client, model)
    duplicates = text(element(html, id='portal-duplicates'))
    assert 'could not check' in duplicates and 'Please try again shortly.' in duplicates
    assert elements(html, id='check-again')
    assert export_button(html) == 'disabled'


def test_duplicates_are_listed_and_block_the_export(model, client, portal):
    portal(by_label={('mass', 'physical quantity'): 'Q5', ('weighing', 'measure a mass'): 'Q6'},
           by_wikidata={'Q7150': 'Q60093'},
           markers={'Q5': markers(), 'Q6': markers(ITEMS['software']), 'Q60093': markers(ITEMS['software'])})
    html = preview_page(client, model)
    assert '3 items are already on the MaRDI Portal' in text(element(html, id='before-export'))
    assert 'Decide on the items already on the MaRDI Portal first' in text(element(html, id='export-blocked'))
    assert export_button(html) == 'disabled'
    rows = {text(element(row, cls='mardmo-item__label')): row for row in elements(html, tag='li', cls='mardmo-duplicate')}
    assert {name: attribute(row, 'data-action') for name, row in rows.items()} == {
        'mass': 'reuse', 'weighing': 'rename', 'ecology': 'replace'}
    # The items with their source
    assert {name: text(element(row, cls='mardmo-source')) for name, row in rows.items()} == {
        'mass': 'new', 'weighing': 'new', 'ecology': 'Wikidata'}
    # Where they are entered (the interview); the portal item to check, without its label
    for row in rows.values():
        assert all(href.startswith(f'/projects/{model.pk}/interview/')
                   for _, href in links(element(row, cls='mardmo-duplicate__where')))
    assert 'QQK1' in text(rows['mass']) and 'CT1' in text(rows['weighing'])
    assert [label for label, _ in links(element(rows['ecology'], cls='mardmo-duplicate__portal'))] == ['Q60093']
    assert 'branch of biology' not in html
    # The quantity may become Q5: only its "Use this item" can be chosen, and its form names the item and Q5
    assert {name: attribute(element(row, tag='input', cls='mardmo-decision__use'), 'disabled') is None
            for name, row in rows.items()} == {'mass': True, 'weighing': False, 'ecology': False}
    form = element(rows['mass'], tag='form')
    assert {attribute(node, 'name'): attribute(node, 'value') for node in elements(form, tag='input', type='hidden')
            if attribute(node, 'name') != 'csrfmiddlewaretoken'} == {'format': 'wikibase', 'item': 'user:mass', 'qid': 'Q5'}
    assert elements(form, tag='input', name='csrfmiddlewaretoken')
    # The task: Q6 is software; the Wikidata field: its twin is software too
    assert 'Its class on the MaRDI Portal is software; MaRDMO would give it the class computational task.' in text(
        element(rows['weighing'], cls='mardmo-why'))
    assert 'a new name would not change its Wikidata QID' in text(element(rows['ecology'], cls='mardmo-why'))


def reuse(client, model, item='user:mass', qid='Q5'):
    return client.post(f'/services/reuse/{model.pk}/', {'format': 'wikibase', 'item': item, 'qid': qid})


def stored(model, path, **fields):
    value = model.values.get(attribute__uri=f'{BASE_URI}domain/{path}', **fields)
    return value.external_id, value.text


def test_use_portal_item_rewrites_every_answer_and_the_page(model, client, portal):
    portal(by_label={('mass', 'physical quantity'): 'Q5'}, markers={'Q5': markers()})
    response = reuse(client, model)
    assert response.status_code == 302 and response.url == f'/projects/{model.pk}/export/wikibase/#before-export'
    assert stored(model, 'quantity/id') == ('mardi:Q5', 'mass (physical quantity)')
    assert stored(model, 'task/quantity-relatant') == ('mardi:Q5', 'mass (physical quantity)')
    assert stored(model, 'quantity/name')[1] == 'mass'
    assert stored(model, 'task/id')[0] == 'user:task'


def test_use_portal_item_takes_the_label_of_a_wikidata_twin(model, client, portal):
    portal(by_wikidata={'Q7150': 'Q60093'}, markers={'Q60093': markers()})
    assert reuse(client, model, 'wikidata:Q7150', 'Q60093').status_code == 302
    assert stored(model, 'field/id') == ('mardi:Q60093', 'ecology (branch of biology)')
    assert stored(model, 'field/description')[1] == 'branch of biology'


@pytest.mark.parametrize('item, qid, found', [
    ('user:mass', 'Q7', {'by_label': {('mass', 'physical quantity'): 'Q5'}, 'markers': {'Q5': {}}}),  # another QID
    ('user:task', 'Q6', {'by_label': {('weighing', 'measure a mass'): 'Q6'},                          # contradicts
                         'markers': {'Q6': markers(ITEMS['software'])}}),
    ('user:mass', 'Q5', {}),                                                                          # no duplicate
])
def test_use_portal_item_is_refused_unless_the_preview_offers_it(model, client, portal, item, qid, found):
    portal(**found)
    assert reuse(client, model, item, qid).status_code == 400
    assert stored(model, 'quantity/id')[0] == 'user:mass' and stored(model, 'task/id')[0] == 'user:task'


def test_use_portal_item_needs_permission_to_change_answers(model, portal, django_user_model):
    portal(by_label={('mass', 'physical quantity'): 'Q5'}, markers={'Q5': markers()})
    guest = django_user_model.objects.create_user('guest', password='guest')
    Membership.objects.create(project=model, user=guest, role='guest')
    client = Client()
    client.force_login(guest)
    assert reuse(client, model).status_code == 403
    assert stored(model, 'quantity/id')[0] == 'user:mass'


def test_use_portal_item_needs_post_and_the_csrf_token(model, portal):
    portal(by_label={('mass', 'physical quantity'): 'Q5'}, markers={'Q5': markers()})
    client = Client(enforce_csrf_checks=True)
    client.force_login(model.values.first().project.owners[0])
    assert client.get(f'/services/reuse/{model.pk}/').status_code == 405
    assert reuse(client, model).status_code == 403
    assert stored(model, 'quantity/id')[0] == 'user:mass'
