'''The LaTeX of the formula and symbol questions, rendered below their fields in RDMO's interview (#190).

MaRDMO's template extends RDMO's interview page with MaRDMO/js/math-preview.js;
the questionnaire marks the formula and symbol questions in their help.  After
a pause in typing, the script asks MaRDMO's tex_check view for the portal's
verdict; here the browser answers it (``verdicts``), the view is
tests/db/test_tex_check_view.py's.  Errors appear when the user stops typing
or leaves the field.
'''
import json
from urllib.parse import parse_qs

import pytest
from playwright.sync_api import expect
from rdmo.projects.models import Membership
from rdmo.questions.models import Page

from MaRDMO.core.constants import BASE_URI
from tests.browser.conftest import screenshot
from tests.db.conftest import answer, save

HINT = '.mardmo-math-preview-hint'
UNVERIFIED = {'state': 'unverified', 'message': '', 'checked': ''}


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


@pytest.fixture
def opened(formula_page, interview_as):
    '''The page opened; the portal's verdicts are answered from ``verdicts`` (else none), ``asked`` notes them.'''
    user, url = formula_page
    page = interview_as(user)
    verdicts, asked = {}, []

    def answer_check(route):
        tex = parse_qs(route.request.post_data or '').get('tex', [''])[0]
        asked.append(tex)
        route.fulfill(status=200, content_type='application/json', body=json.dumps(verdicts.get(tex, UNVERIFIED)))
    page.route('**/services/tex-check/', answer_check)
    page.goto(url)
    return page, verdicts, asked


def question(page, text):
    return page.locator('.interview-question', has=page.locator('.interview-question-text', has_text=text))


def formula_field(page):
    formula = question(page, 'Defining Formula')
    field = formula.locator('.interview-input input').first
    field.wait_for(timeout=30000)
    return formula, field, formula.locator('.mardmo-math-preview')


def test_a_formula_is_rendered_below_its_field(opened):
    page, verdicts, asked = opened
    formula, field, preview = formula_field(page)
    field.fill(r'F = m \cdot \frac{\mathrm{d}v}{\mathrm{d}t}')
    expect(preview.locator('mjx-container')).to_have_count(1, timeout=30000)
    screenshot(formula, 'math-preview')

    # A TeX extension MathJax loads when a formula needs it (from MaRDMO's MathJax, whose URL has RDMO's ?v=)
    field.fill(r'\cancel{x} + \ce{H2O}')
    expect(preview.locator('mjx-container')).to_have_count(1, timeout=30000)
    expect(preview.locator('mjx-merror')).to_have_count(0)
    expect(preview.locator(HINT)).to_have_count(0)

    # MathJax cannot render it, and there is no verdict of the portal: MathJax's message, as a hint
    field.fill(r'\frac{a}{b')
    expect(preview.locator(HINT)).to_contain_text('MathJax cannot show this formula', timeout=30000)
    expect(preview.locator('mjx-container')).to_have_count(0)
    # No verdict: nothing for the user about it, only in the page
    expect(preview).to_have_attribute('data-check', 'unverified')
    screenshot(formula, 'math-preview-error')

    # Emptied: nothing
    field.fill('')
    expect(preview).to_be_empty(timeout=30000)


def test_the_portals_message_where_it_does_not_accept_the_formula(opened):
    page, verdicts, asked = opened
    formula, field, preview = formula_field(page)
    tex = r'\begin{gather} a = b \end{gather}'
    verdicts[tex] = {'state': 'invalid', 'checked': '',
                     'message': 'syntax error (gather is not supported; supported environments are aligned, …)'}
    field.fill(tex)
    # MathJax renders it; the portal does not accept it
    expect(preview.locator(HINT)).to_contain_text(
        'The MaRDI Portal does not accept this formula: syntax error (gather is not supported', timeout=30000)
    expect(preview.locator('mjx-container')).to_have_count(1)
    expect(preview).to_have_attribute('data-check', 'invalid')
    assert asked == [tex]
    screenshot(formula, 'math-preview-portal')


def test_an_unknown_command_is_an_error(opened):
    '''A typo such as \\fracc gets MathJax's message (not MathJax's red text).'''
    page, verdicts, asked = opened
    formula, field, preview = formula_field(page)
    field.fill(r'\fracc{a}{b}')
    expect(preview.locator(HINT)).to_contain_text(r'\fracc', timeout=30000)
    expect(preview.locator('mjx-container')).to_have_count(0)


def test_what_only_the_portal_knows_is_rendered_in_its_form(opened):
    '''\\R is a shorthand of the portal's checker, unknown to MathJax: the checker's form is rendered.'''
    page, verdicts, asked = opened
    formula, field, preview = formula_field(page)
    # Without the portal's verdict: MathJax's message
    field.fill(r'y \in \R')
    expect(preview.locator(HINT)).to_contain_text(r'\R', timeout=30000)
    # The portal accepts it
    verdicts[r'x \in \R'] = {'state': 'valid', 'message': '', 'checked': r'x\in \mathbb{R}'}
    field.fill(r'x \in \R')
    expect(preview).to_have_attribute('data-check', 'valid', timeout=30000)
    expect(preview.locator('mjx-container')).to_have_count(1, timeout=30000)
    expect(preview.locator('mjx-merror')).to_have_count(0)
    page.wait_for_timeout(2500)
    expect(preview.locator(HINT)).to_have_count(0)
    # The field keeps what was typed
    expect(field).to_have_value(r'x \in \R')


def test_no_error_while_typing_and_no_request_per_key(opened):
    page, verdicts, asked = opened
    formula, field, preview = formula_field(page)
    field.fill('a = b')
    expect(preview.locator('mjx-container')).to_have_count(1, timeout=30000)
    expect(preview).to_have_attribute('data-check', 'unverified', timeout=30000)
    field.click()
    page.keyboard.press('End')
    # Typing on: what is half-typed cannot be rendered, the last formula stays, dimmed, without an error
    page.keyboard.type(r' \begin{align} c &= d', delay=60)
    expect(preview.locator('.mardmo-math-preview-stale mjx-container')).to_have_count(1, timeout=5000)
    expect(preview.locator(HINT)).to_have_count(0)
    # The user stops: now the error
    expect(preview.locator(HINT)).to_contain_text('MathJax cannot show this formula', timeout=10000)
    expect(preview.locator('.mardmo-math-preview-stale')).to_have_count(0)
    # The portal was asked after the pauses, not for every key
    assert len(asked) <= 2, asked


def test_leaving_the_field_shows_the_error_at_once(opened):
    page, verdicts, asked = opened
    formula, field, preview = formula_field(page)
    field.click()
    page.keyboard.type(r'\frac{a}{b', delay=20)
    page.keyboard.press('Tab')
    # Before the pause after which it would appear anyway
    expect(preview.locator(HINT)).to_contain_text('MathJax cannot show this formula', timeout=1200)


def test_questions_without_the_marker_get_no_rendering(opened):
    page, verdicts, asked = opened
    name = question(page, 'Name of the Formula')
    field = name.locator('.interview-input input').first
    field.wait_for(timeout=30000)
    field.fill(r'\alpha')
    page.wait_for_timeout(2500)
    expect(name.locator('.mardmo-math-preview')).to_have_count(0)
    assert asked == []
