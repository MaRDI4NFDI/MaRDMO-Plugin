'''The LaTeX of the formula and symbol questions, rendered below their fields in RDMO's interview.

MaRDMO's template extends RDMO's interview page with MaRDMO/js/math-preview.js;
the questionnaire marks the formula and symbol questions in their help.  What
MathJax cannot render is shown with its message, as a hint.
'''
import pytest
from playwright.sync_api import expect
from rdmo.projects.models import Membership
from rdmo.questions.models import Page

from MaRDMO.constants import BASE_URI
from tests.browser.conftest import screenshot
from tests.db.conftest import answer, save


@pytest.fixture
def formula_page(project, django_user_model):
    '''The formula page of a model documentation with one tab, nothing filled.'''
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    save(documentation, answer('formulation', 'F1', set_index=0))
    page = Page.objects.filter(attribute__uri=f'{BASE_URI}domain/formulation',
                               sections__catalogs=documentation.catalog).first()
    return user, f'/projects/{documentation.pk}/interview/{page.pk}/'


def question(page, text):
    return page.locator('.interview-question', has=page.locator('.interview-question-text', has_text=text))


def test_a_formula_is_rendered_below_its_field(formula_page, interview_as):
    user, url = formula_page
    page = interview_as(user)
    page.goto(url)
    formula = question(page, 'Defining Formula of the Formula')
    field = formula.locator('.interview-input input').first
    field.wait_for(timeout=30000)
    field.fill(r'F = m \cdot \frac{\mathrm{d}v}{\mathrm{d}t}')
    preview = formula.locator('.mardmo-math-preview')
    expect(preview.locator('mjx-container')).to_have_count(1, timeout=30000)
    screenshot(formula, 'math-preview')

    # A TeX extension MathJax loads when a formula needs it (from MaRDMO's MathJax, whose URL has RDMO's ?v=)
    field.fill(r'\cancel{x} + \ce{H2O}')
    expect(preview.locator('mjx-container')).to_have_count(1, timeout=30000)
    expect(preview.locator('mjx-merror')).to_have_count(0)
    expect(preview.locator('.mardmo-math-preview-hint')).to_have_count(0)

    # MathJax cannot render it: its message, as a hint
    field.fill(r'\frac{a}{b')
    expect(preview.locator('.mardmo-math-preview-hint')).to_contain_text('MathJax cannot show this formula', timeout=30000)
    expect(preview.locator('mjx-container')).to_have_count(0)
    screenshot(formula, 'math-preview-error')

    # Emptied: nothing
    field.fill('')
    expect(preview).to_be_empty(timeout=30000)


def test_questions_without_the_marker_get_no_rendering(formula_page, interview_as):
    user, url = formula_page
    page = interview_as(user)
    page.goto(url)
    name = question(page, 'Name of the Formula')
    field = name.locator('.interview-input input').first
    field.wait_for(timeout=30000)
    field.fill(r'\alpha')
    page.wait_for_timeout(1000)
    expect(name.locator('.mardmo-math-preview')).to_have_count(0)
