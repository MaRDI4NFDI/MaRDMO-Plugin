'''The preview runs everything the export checks and offers the export only when nothing is left (#152).

white_2006 is complete: its preview offers the export.  Changed, it lists
what the checks find, linked to the pages, and the export button is
disabled; what only the export's own checks find (a symbol that stands for
another quantity on the portal) is listed too.  The export runs it all
once more: what it finds changed since the preview.
'''
from rdmo.questions.models import Page

from MaRDMO.constants import BASE_URI
from MaRDMO.payload import DocumentationProblem, GeneratePayload, PortalUnavailable
from tests.db.conftest import without_description
from tests.support.html import element, elements, export_button, export_page, links, preview_page, text


def test_complete_documentation_can_be_exported(white, client):
    html = preview_page(client, white)
    assert not elements(html, id='before-export') and not elements(html, id='export-blocked')
    assert export_button(html) == 'enabled'


def test_problems_are_listed_with_links_and_the_export_is_disabled(white, client):
    without_description(white, 'formulation', 1)
    html = preview_page(client, white)
    problems = element(html, id='export-problems')
    assert 'Formula, conservation law for the opiate-using career ODE model (F2)' in text(problems)
    assert 'Missing Short Description' in text(problems)
    # Linked to the page in the preview, and to the interview page of the formulas (RDMO opens the page, the tab is named)
    page = Page.objects.get(attribute__uri=f'{BASE_URI}domain/formulation', sections__catalogs=white.catalog)
    assert links(problems) == [('conservation law for the opiate-using career ODE model', '#page-formulation-1'),
                               ('To interview', f'/projects/{white.pk}/interview/{page.pk}/')]
    assert elements(html, id='page-formulation-1')
    assert '1 point to fix in the documentation' in text(element(html, id='before-export'))
    assert export_button(html) == 'disabled'
    assert 'Fix the points at the top (Before you export)' in text(element(html, id='export-blocked'))


def test_what_only_the_export_finds_is_listed(white, client, monkeypatch):
    def conflict(self, api_url, deadline=None):
        raise DocumentationProblem('"F1": on the MaRDI Portal the symbol S already stands for Q1.')
    monkeypatch.setattr(GeneratePayload, 'check_symbols', conflict)
    html = preview_page(client, white)
    problems = text(element(html, id='export-problems'))
    assert 'Export' in problems and 'the symbol S already stands for Q1' in problems
    assert export_button(html) == 'disabled'


def test_an_unreachable_portal_asks_to_try_again(white, client, monkeypatch):
    def unreachable(self, *args):
        raise PortalUnavailable('Could not check which statements already exist on the MaRDI Portal.')
    monkeypatch.setattr(GeneratePayload, '_fetch_claims', unreachable)
    html = preview_page(client, white)
    problems = text(element(html, id='export-problems'))
    assert 'Could not check which statements already exist' in problems and 'Please try again shortly.' in problems
    assert elements(html, id='check-again')
    assert export_button(html) == 'disabled'


def test_an_unanswered_tex_check_asks_to_try_again(white, client, monkeypatch):
    monkeypatch.setattr('MaRDMO.checks.model.check_formulas',
                        lambda formulas: {tex: 'unavailable' for tex in formulas})
    monkeypatch.setattr('MaRDMO.checks.model.UNAVAILABLE', 'unavailable')
    html = preview_page(client, white)
    assert 'The TeX check of the MaRDI Portal did not answer' in text(html) and export_button(html) == 'disabled'


def test_a_formula_the_tex_check_fails_on_passes_unverified(white, client, monkeypatch):
    '''The checker fails on a formula (e.g. HTTP 500 for valid TeX, #165): no dead end, a note.'''
    monkeypatch.setattr('MaRDMO.checks.model.check_formulas', lambda formulas: {tex: 'failed' for tex in formulas})
    monkeypatch.setattr('MaRDMO.tex_check.check_formulas', lambda formulas: {tex: 'failed' for tex in formulas})
    html = preview_page(client, white)
    assert not elements(html, id='before-export') and export_button(html) == 'enabled'
    assert "TeX check failed on this formula; it is exported unchecked" in text(html)


def test_the_export_checks_again_and_names_what_changed(white, client):
    assert export_button(preview_page(client, white)) == 'enabled'
    without_description(white, 'formulation', 1)       # after the preview
    page = text(export_page(client, white).content.decode())
    assert 'Something changed since the preview' in page
    assert 'Formula (Page F2): Missing Short Description' in page


def test_a_missing_relation_is_marked_not_not_documented(white, client):
    '''An empty relation is "NOT DOCUMENTED" only if it may be empty; a missing one shows just its mark.'''
    html = preview_page(client, white)
    block = html[html.index('id="RP2AD"'):]
    assert 'NOT DOCUMENTED' not in block[:block.index('<h')]
    white.values.filter(attribute__uri=f'{BASE_URI}domain/problem/field-relatant').delete()
    html = preview_page(client, white)
    block = html[html.index('id="RP2AD"'):]
    block = block[:block.index('<h', 1)]
    assert 'Missing Academic Discipline' in text(block) and 'NOT DOCUMENTED' not in block


def test_only_hints_leave_the_export_possible(white, client):
    '''A portal quantity without short description (#167): listed as optional, blue at its field, export enabled.'''
    without_description(white, 'quantity', 3)
    html = preview_page(client, white)
    box = element(html, id='before-export')
    assert 'mardmo-before-export--optional' in box.attributes['class']
    assert 'Nothing prevents the export' in text(box) and '1 portal item could be completed' in text(box)
    hints = element(html, id='portal-hints')
    assert 'Quantity [Kind], number of susceptible individuals' in text(hints) and 'Missing Short Description' in text(hints)
    assert not elements(html, id='export-problems')
    assert export_button(html) == 'enabled'
    assert '<strong class="mardmo-hint">Missing Short Description</strong>' in html
