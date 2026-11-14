'''The preview's section "Already on the MaRDI Portal" in a browser (#141).'''
import os

import pytest
from rdmo.projects.models import Membership

from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_items
from MaRDMO.queries import PortalItems
from tests.db.conftest import answer, save

ITEMS = get_items()
# SCREENSHOTS=<folder> saves pictures of the section
SCREENSHOTS = os.environ.get('SCREENSHOTS')


def screenshot(locator, name):
    if SCREENSHOTS:
        locator.screenshot(path=os.path.join(SCREENSHOTS, f'{name}.png'))
EMPTY = {'class': set(), 'community': set(), 'profile': set()}


@pytest.fixture
def documentation(project, django_user_model, monkeypatch):
    '''A quantity used by a task; the portal has the quantity (reusable) and the task (as software).'''
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    found = PortalItems(by_label={('mass', 'physical quantity'): 'Q5', ('weighing', 'measure a mass'): 'Q6'},
                        markers={'Q5': EMPTY, 'Q6': {**EMPTY, 'class': {ITEMS['software']}}})

    def find(pairs=(), **kwargs):
        # After the reuse the quantity is a portal item: no longer asked for
        return PortalItems(by_label={pair: qid for pair, qid in found.by_label.items() if pair in pairs},
                           markers=found.markers)
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', find)
    model = project('mardmo-model-catalog')
    owner = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=model, user=owner, role='owner')
    save(model,
         answer('quantity', 'QQK1', set_index=0),
         answer('quantity/id', 'new item', external_id='user:mass', set_index=0),
         answer('quantity/name', 'mass', set_prefix='0'),
         answer('quantity/description', 'physical quantity', set_prefix='0'),
         answer('task', 'CT1', set_index=0),
         answer('task/id', 'new item', external_id='user:task', set_index=0),
         answer('task/name', 'weighing', set_prefix='0'),
         answer('task/description', 'measure a mass', set_prefix='0'),
         answer('task/quantity-relatant', 'mass (physical quantity)', external_id='user:mass', set_prefix='0|0'))
    return model, owner


def test_use_portal_item_in_the_browser(documentation, page_as):
    model, owner = documentation
    page = page_as(owner)
    page.goto(f'/projects/{model.pk}/export/wikibase/')

    section = page.locator('#portal-duplicates')
    screenshot(section, 'portal-duplicates')
    assert section.locator('h1').inner_text() == 'Already on the MaRDI Portal'
    rows = section.locator('tr.mardmo-duplicate')
    assert rows.count() == 2
    assert page.locator('#export-blocked').is_visible()
    assert page.locator('input[type=submit][value="Export to MaRDI Portal"]').count() == 0

    # The page of the item: the interview, in a new window
    link = rows.filter(has_text='mass').locator('a', has_text='Quantity')
    assert link.get_attribute('target') == '_blank'
    assert f'/projects/{model.pk}/interview/' in link.get_attribute('href')

    # The task cannot become software; the quantity can become Q5
    assert rows.filter(has_text='weighing').locator('button').count() == 0
    assert 'MaRDMO would give it the class computational task' in rows.filter(has_text='weighing').inner_text()
    rows.filter(has_text='mass').get_by_role('button', name='Use portal item').click()
    page.wait_for_load_state()

    # Back on the preview: one row left, still no export
    assert page.url.endswith(f'/projects/{model.pk}/export/wikibase/')
    assert page.locator('tr.mardmo-duplicate').count() == 1
    screenshot(page.locator('#portal-duplicates'), 'portal-duplicates-after-reuse')
    assert page.locator('tr.mardmo-duplicate').inner_text().count('weighing')
    quantity = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity/id')
    relation = model.values.get(attribute__uri=f'{BASE_URI}domain/task/quantity-relatant')
    assert (quantity.external_id, relation.external_id) == ('mardi:Q5', 'mardi:Q5')


def test_without_duplicates_the_export_button_is_back(documentation, page_as, monkeypatch):
    model, owner = documentation
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: PortalItems())
    page = page_as(owner)
    page.goto(f'/projects/{model.pk}/export/wikibase/')
    assert page.locator('#portal-duplicates').count() == 0
    assert page.locator('input[type=submit][value="Export to MaRDI Portal"]').is_visible()


def test_a_guest_sees_no_preview_and_a_post_without_token_is_refused(documentation, page_as, django_user_model):
    """Guests may not export (RDMO); the permission of the reuse itself: tests/db/test_portal_duplicates.py."""
    model, _ = documentation
    guest = django_user_model.objects.create_user('guest', password='guest')
    Membership.objects.create(project=model, user=guest, role='guest')
    page = page_as(guest)
    assert page.goto(f'/projects/{model.pk}/export/wikibase/').status == 403
    response = page.request.post(f'/services/reuse/{model.pk}/',
                                 form={'format': 'wikibase', 'item': 'user:mass', 'qid': 'Q5'})
    assert response.status == 403
    assert model.values.get(attribute__uri=f'{BASE_URI}domain/quantity/id').external_id == 'user:mass'
