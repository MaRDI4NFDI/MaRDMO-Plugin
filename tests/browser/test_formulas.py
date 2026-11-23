'''Formulas in the preview, rendered by MathJax in a browser (_mathjax_errors.html).

A formula MathJax can render is shown as mathematics; one it cannot is shown
as raw TeX with MathJax's message instead of MathJax's red error box.
'''
from playwright.sync_api import expect

from MaRDMO.core.constants import BASE_URI
from tests.browser.conftest import screenshot
from tests.db.conftest import portal, white  # noqa: F401 (white_2006, complete; its recorded portal)
from tests.support.html import PREVIEW_URL


def mathjax_ready(page):
    page.wait_for_function('window.MathJax && MathJax.startup && MathJax.startup.promise')
    page.evaluate('() => MathJax.startup.promise')


def test_formulas_are_rendered(white, page_as):  # noqa: F811
    owner = white.memberships.get(role='owner').user
    page = page_as(owner)
    page.goto(PREVIEW_URL.format(white.pk))
    mathjax_ready(page)
    formulas = page.locator('.mardmo-formula')
    assert formulas.count() > 0
    expect(formulas.first.locator('mjx-container')).to_have_count(1)
    assert page.locator('mjx-merror').count() == 0
    assert 'FORMULA CANNOT BE DISPLAYED' not in page.locator('.mardmo-preview').inner_text()


def test_a_formula_mathjax_cannot_render_is_shown_as_tex(white, page_as):  # noqa: F811
    formula = white.values.filter(attribute__uri=f'{BASE_URI}domain/formulation/formula').order_by('set_prefix').first()
    formula.text = r'\frac{a}{b'
    formula.save()
    owner = white.memberships.get(role='owner').user
    page = page_as(owner)
    page.goto(PREVIEW_URL.format(white.pk))
    mathjax_ready(page)
    raw = page.locator('code.mardmo-tex', has_text=r'\frac{a}{b')
    expect(raw).to_have_count(1)
    expect(raw.locator('xpath=..')).to_contain_text('FORMULA CANNOT BE DISPLAYED')
    assert page.locator('mjx-merror').count() == 0
    screenshot(raw.locator('xpath=..'), 'formula-cannot-be-displayed')
