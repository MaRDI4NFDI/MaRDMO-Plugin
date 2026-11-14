'''The preview's section "Already on the MaRDI Portal" and its "use portal item" (#141).

The portal's answers are faked: find_portal_items finds what a test gives it.
'''
import pytest
from django.test import Client
from rdmo.projects.models import Membership

from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_items
from MaRDMO.queries import PortalItems
from tests.db.conftest import answer, save

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


def preview(client, model):
    response = client.get(f'/projects/{model.pk}/export/wikibase/')
    assert response.status_code == 200
    return response.content.decode()


def test_without_duplicates_the_preview_has_no_section_and_exports(model, client, portal):
    portal()
    html = preview(client, model)
    assert 'Already on the MaRDI Portal' not in html
    assert 'Export to MaRDI Portal' in html and 'export-blocked' not in html


def test_a_failed_lookup_is_noted_and_the_export_checks_again(model, client, portal):
    portal(label_failed=True)
    html = preview(client, model)
    assert 'could not check' in html and 'Export to MaRDI Portal' in html


def test_duplicates_are_listed_and_block_the_export(model, client, portal):
    portal(by_label={('mass', 'physical quantity'): 'Q5', ('weighing', 'measure a mass'): 'Q6'},
           by_wikidata={'Q7150': 'Q60093'},
           markers={'Q5': markers(), 'Q6': markers(ITEMS['software']), 'Q60093': markers(ITEMS['software'])})
    html = preview(client, model)
    assert 'Already on the MaRDI Portal' in html
    assert 'id="export-blocked"' in html and 'type="submit" value="Export to MaRDI Portal"' not in html
    # The quantity may become Q5: a form with the CSRF token
    assert html.count('data-action="reuse"') == 1 and 'csrfmiddlewaretoken' in html
    assert 'name="item" value="user:mass"' in html and 'name="qid" value="Q5"' in html
    # The task: Q6 is software; the Wikidata field: its twin is software too
    assert 'data-action="rename"' in html and 'data-action="replace"' in html
    assert 'Its class on the MaRDI Portal is software; MaRDMO would give it the class computational task.' in html
    # Where: the page and the tab's name; the twin's portal label
    assert f'/projects/{model.pk}/interview/' in html and 'QQK1' in html and 'CT1' in html
    assert 'ecology (branch of biology)' in html


def reuse(client, model, item='user:mass', qid='Q5'):
    return client.post(f'/services/reuse/{model.pk}/', {'format': 'wikibase', 'item': item, 'qid': qid})


def text(model, path, **fields):
    value = model.values.get(attribute__uri=f'{BASE_URI}domain/{path}', **fields)
    return value.external_id, value.text


def test_use_portal_item_rewrites_every_answer_and_the_page(model, client, portal):
    portal(by_label={('mass', 'physical quantity'): 'Q5'}, markers={'Q5': markers()})
    response = reuse(client, model)
    assert response.status_code == 302 and response.url == f'/projects/{model.pk}/export/wikibase/'
    assert text(model, 'quantity/id') == ('mardi:Q5', 'mass (physical quantity)')
    assert text(model, 'task/quantity-relatant') == ('mardi:Q5', 'mass (physical quantity)')
    assert text(model, 'quantity/name')[1] == 'mass'
    assert text(model, 'task/id')[0] == 'user:task'


def test_use_portal_item_takes_the_label_of_a_wikidata_twin(model, client, portal):
    portal(by_wikidata={'Q7150': 'Q60093'}, markers={'Q60093': markers()})
    assert reuse(client, model, 'wikidata:Q7150', 'Q60093').status_code == 302
    assert text(model, 'field/id') == ('mardi:Q60093', 'ecology (branch of biology)')
    assert text(model, 'field/description')[1] == 'branch of biology'


@pytest.mark.parametrize('item, qid, found', [
    ('user:mass', 'Q7', {'by_label': {('mass', 'physical quantity'): 'Q5'}, 'markers': {'Q5': {}}}),  # another QID
    ('user:task', 'Q6', {'by_label': {('weighing', 'measure a mass'): 'Q6'},                          # contradicts
                         'markers': {'Q6': markers(ITEMS['software'])}}),
    ('user:mass', 'Q5', {}),                                                                          # no duplicate
])
def test_use_portal_item_is_refused_unless_the_preview_offers_it(model, client, portal, item, qid, found):
    portal(**found)
    assert reuse(client, model, item, qid).status_code == 400
    assert text(model, 'quantity/id')[0] == 'user:mass' and text(model, 'task/id')[0] == 'user:task'


def test_use_portal_item_needs_permission_to_change_answers(model, portal, django_user_model):
    portal(by_label={('mass', 'physical quantity'): 'Q5'}, markers={'Q5': markers()})
    guest = django_user_model.objects.create_user('guest', password='guest')
    Membership.objects.create(project=model, user=guest, role='guest')
    client = Client()
    client.force_login(guest)
    assert reuse(client, model).status_code == 403
    assert text(model, 'quantity/id')[0] == 'user:mass'


def test_use_portal_item_needs_post_and_the_csrf_token(model, portal):
    portal(by_label={('mass', 'physical quantity'): 'Q5'}, markers={'Q5': markers()})
    client = Client(enforce_csrf_checks=True)
    client.force_login(model.values.first().project.owners[0])
    assert client.get(f'/services/reuse/{model.pk}/').status_code == 405
    assert reuse(client, model).status_code == 403
    assert text(model, 'quantity/id')[0] == 'user:mass'
