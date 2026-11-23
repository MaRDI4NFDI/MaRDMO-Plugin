'''The preview's items already on the MaRDI Portal (Before you export) in a browser (#141).'''
import re

import pytest
from rdmo.projects.models import Membership

from MaRDMO.core.constants import BASE_URI
from MaRDMO.core.config import get_items
from MaRDMO.sources.portal import PortalItems
from tests.browser.conftest import screenshot
from tests.db.conftest import answer, save

ITEMS = get_items()
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

    box = page.locator('#before-export')
    screenshot(page, 'duplicates-top')
    screenshot(box, 'duplicates-box')
    assert box.locator('h1').inner_text().endswith('Before you export')
    section = box.locator('#portal-duplicates')
    assert section.locator('h2').inner_text() == 'Items already on the MaRDI Portal'
    rows = section.locator('li.mardmo-duplicate')
    assert rows.count() == 2
    # Why the export button is disabled: its hover text; a button back to the top
    assert 'Decide on the items already on the MaRDI Portal first' in page.locator('.mardmo-blocked').get_attribute('title')
    assert page.locator('input[type=submit][value="Export to MaRDI Portal"]').is_disabled()
    assert page.get_by_role('button', name='To the top').is_visible()
    # The project's title above the box
    assert page.locator('#title').inner_text() == model.title
    assert page.locator('#title').bounding_box()['y'] < box.bounding_box()['y']

    def row(label):
        return rows.filter(has=page.locator('.mardmo-item__label', has_text=re.compile(f'^{label}$')))
    mass, weighing = row('mass'), row('weighing')
    assert mass.locator('.mardmo-source').inner_text() == 'new'
    # The page of the item: the interview, in a new window; the portal item to check
    link = mass.locator('.mardmo-duplicate__where a', has_text='Quantity')
    assert link.get_attribute('target') == '_blank'
    assert f'/projects/{model.pk}/interview/' in link.get_attribute('href')
    assert mass.locator('.mardmo-duplicate__portal a').inner_text() == 'Q5'

    # Nothing chosen: no button.  The task cannot become software: only "Redefine", and why (hover, and the (i))
    assert not mass.get_by_role('button', name='Apply').is_visible()
    assert not mass.get_by_role('link', name='To interview').is_visible()
    assert weighing.get_by_label('Use this item').is_disabled()
    assert 'MaRDMO would give it the class computational task' in weighing.locator(
        'label', has_text='Use this item').get_attribute('title')
    why = weighing.locator('.mardmo-why__text')
    assert not why.is_visible()
    weighing.locator('.mardmo-why summary').click()
    assert why.is_visible() and 'MaRDMO would give it the class computational task' in why.inner_text()
    screenshot(box, 'duplicates-why')
    weighing.locator('.mardmo-why summary').click()
    assert not why.is_visible()
    assert mass.locator('.mardmo-why').count() == 0
    weighing.locator('label', has_text='Redefine').click()
    to_interview = weighing.get_by_role('link', name='To interview')
    assert to_interview.is_visible() and to_interview.get_attribute('target') == '_blank'
    assert f'/projects/{model.pk}/interview/' in to_interview.get_attribute('href')

    # The quantity can become Q5: choosing shows "Apply", which does it
    mass.locator('label', has_text='Use this item').click()
    assert mass.get_by_role('button', name='Apply').is_visible()
    assert not mass.get_by_role('link', name='To interview').is_visible()
    screenshot(box, 'duplicates-decisions')
    screenshot(page, 'duplicates-preview', full_page=True)
    mass.get_by_role('button', name='Apply').click()
    page.wait_for_load_state()

    # Back on the preview: one item left, still no export
    assert page.url.endswith(f'/projects/{model.pk}/export/wikibase/#before-export')
    assert page.locator('li.mardmo-duplicate').count() == 1
    screenshot(page.locator('#before-export'), 'duplicates-after-reuse')
    assert page.locator('li.mardmo-duplicate').inner_text().count('weighing')
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
