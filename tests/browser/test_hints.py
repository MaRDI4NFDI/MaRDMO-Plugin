'''What a portal item could have, in the preview in a browser (#167).

A portal quantity of white_2006 without short description: the box above
the preview is not a warning, its blue part lists the quantity, the mark at
the quantity is blue, and the export button can be clicked.
'''
from playwright.sync_api import expect

from tests.browser.conftest import screenshot
from tests.db.conftest import portal, white, without_description  # noqa: F401 (white_2006 and its recorded portal)
from tests.support.html import PREVIEW_URL


def test_hints_are_blue_and_the_export_stays_possible(white, page_as):  # noqa: F811
    without_description(white, 'quantity', 3)
    page = page_as(white.memberships.get(role='owner').user)
    page.goto(PREVIEW_URL.format(white.pk))
    box = page.locator('#before-export')
    expect(box).to_have_class('mardmo-before-export mardmo-before-export--optional')
    expect(box.locator('h1')).to_contain_text('Before you export')
    hints = page.locator('#portal-hints')
    expect(hints).to_contain_text('number of susceptible individuals')
    expect(hints.locator('.mardmo-hint')).to_have_text(['Missing Short Description'])
    # Blue, not red: the colour the page shows
    assert hints.locator('.mardmo-hint').evaluate('node => getComputedStyle(node).color') == 'rgb(31, 111, 178)'
    expect(page.locator('#export-problems')).to_have_count(0)
    expect(page.get_by_role('button', name='Export to MaRDI Portal')).to_be_enabled()
    screenshot(box, 'portal-hints')
