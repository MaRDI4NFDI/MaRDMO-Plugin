'''MaRDMO's dropdowns in RDMO's interview: badge, label and description; the answer stays plain (#142).

The options come from MaRDMO's provider and query layer as in the
interview; only the searches of the MaRDI Portal and Wikidata are given.
The open list shows each option's source as a badge, its label and its
description, not its plain text; the stored answer and the filled field are
the plain "Label (Description)".  This also fails if RDMO stops rendering
the options' help as HTML.
'''
import pytest
from rdmo.projects.models import Membership
from rdmo.questions.models import Page

import MaRDMO.components.dropdowns as dropdowns
from MaRDMO import router
from MaRDMO.core.constants import BASE_URI
from tests.browser.conftest import screenshot
from tests.db.conftest import answer, save

PORTAL = [{'id': 'mardi:Q5', 'text': 'mass (property of matter)'}]
# The portal is searched by class or by profile (quantities: by profile, #170)
FOUND = {'mardi': PORTAL, 'mardi-profiles': PORTAL,
         'wikidata': [{'id': 'Q11423', 'display': {'label': {'value': 'mass'},
                                                   'description': {'value': 'property of physical bodies'}}}]}


@pytest.fixture
def interview(project, django_user_model, monkeypatch):
    '''The quantity page of a model documentation with one tab; the searches are given, nothing is filled.'''
    monkeypatch.setattr(dropdowns, '_cached_search', lambda source, *args: FOUND[source])
    # The Wikidata hit is a quantity (class check, #170)
    monkeypatch.setattr(dropdowns, 'wikidata_matches', lambda items, **kwargs: {item: True for item in items})
    monkeypatch.setitem(router.HANDLER_MAP['mardmo-model-catalog'], f'{BASE_URI}domain/quantity/id',
                        lambda instance: None)
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    save(documentation, answer('quantity', 'Q1', set_index=0))
    page = Page.objects.filter(attribute__uri=f'{BASE_URI}domain/quantity',
                               sections__catalogs=documentation.catalog).first()
    return documentation, user, f'/projects/{documentation.pk}/interview/{page.pk}/'


def test_the_options_show_badge_label_and_description(interview, interview_as):
    documentation, user, url = interview
    page = interview_as(user)
    page.goto(url)
    field = page.locator('.react-select__input').first
    field.wait_for(timeout=30000)
    field.click()
    field.fill('mass')
    options = page.locator('.react-select__option')
    options.nth(2).wait_for(timeout=30000)
    screenshot(page.locator('.react-select__menu'), 'dropdown-options')

    # new item, then the portal's and Wikidata's: badge, label, description; not the plain text
    shown = [text.split('\n') for text in options.all_inner_texts()]
    assert shown == [['new item'], ['mardimass', 'property of matter'], ['wikidatamass', 'property of physical bodies']]
    assert options.nth(1).locator('.mardmo-option span').first.inner_text() == 'mardi'

    # The field shows the choice at once; the answer is stored by the request that follows
    with page.expect_response(lambda response: '/values/' in response.url
                              and response.request.method in ('POST', 'PUT'), timeout=30000) as saved:
        options.nth(2).click()
    assert saved.value.ok
    page.wait_for_function(
        "document.querySelector('.react-select__single-value')?.innerText === 'mass (property of physical bodies)'",
        timeout=30000)
    stored = documentation.values.get(attribute__uri=f'{BASE_URI}domain/quantity/id', set_index=0)
    assert (stored.external_id, stored.text) == ('wikidata:Q11423', 'mass (property of physical bodies)')
    screenshot(page.locator('.react-select').first, 'dropdown-filled')
