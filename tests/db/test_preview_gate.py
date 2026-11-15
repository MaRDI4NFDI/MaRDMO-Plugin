'''The preview runs everything the export checks and offers the export only when nothing is left (#152).

white_2006 is complete: its preview offers the export.  Changed, it lists
what the checks find, linked to the pages, and the export button is
disabled; what only the export's own checks find (a symbol that stands for
another quantity on the portal) is listed too.  The export runs it all
once more: what it finds changed since the preview.
'''
import re

from MaRDMO.constants import BASE_URI
from MaRDMO.payload import DocumentationProblem, GeneratePayload, PortalUnavailable

URL = '/projects/{}/export/wikibase/'
BUTTON = '<input type="submit" value="Export to MaRDI Portal" class="btn btn-primary"'


def preview(client, documentation):
    response = client.get(URL.format(documentation.pk))
    assert response.status_code == 200
    return response.content.decode()


def text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def without_description(documentation, section, index):
    documentation.values.filter(attribute__uri=f'{BASE_URI}domain/{section}/description',
                                set_prefix=str(index)).delete()


def test_complete_documentation_can_be_exported(white, client):
    html = preview(client, white)
    assert 'Before you can export' not in html and 'export-blocked' not in html
    assert f'{BUTTON} />' in html


def test_problems_are_listed_with_links_and_the_export_is_disabled(white, client):
    without_description(white, 'formulation', 1)
    html = preview(client, white)
    assert 'Before you can export' in html
    section = html[html.index('id="export-problems"'):html.index('</div>', html.index('id="export-problems"'))]
    assert '<a href="#page-formulation-1">conservation law for the opiate-using career ODE model</a> (F2)' in section
    assert 'Missing Short Description' in text(section)
    assert 'id="page-formulation-1"' in html
    assert f'{BUTTON} disabled aria-describedby="export-blocked" />' in html
    assert 'Fix the points at the top (Before you can export)' in text(html)


def test_what_only_the_export_finds_is_listed(white, client, monkeypatch):
    def conflict(self, api_url, deadline=None):
        raise DocumentationProblem('"F1": on the MaRDI Portal the symbol S already stands for Q1.')
    monkeypatch.setattr(GeneratePayload, 'check_symbols', conflict)
    html = preview(client, white)
    assert 'Export' in text(html) and 'the symbol S already stands for Q1' in text(html)
    assert f'{BUTTON} disabled' in html


def test_an_unreachable_portal_asks_to_try_again(white, client, monkeypatch):
    def unreachable(self, *args):
        raise PortalUnavailable('Could not check which statements already exist on the MaRDI Portal.')
    monkeypatch.setattr(GeneratePayload, '_fetch_claims', unreachable)
    html = preview(client, white)
    assert 'Could not check which statements already exist' in html
    assert 'Please try again shortly.' in html and 'id="check-again"' in html
    assert f'{BUTTON} disabled' in html


def test_an_unanswered_tex_check_asks_to_try_again(white, client, monkeypatch):
    monkeypatch.setattr('MaRDMO.checks.model.check_formulas',
                        lambda formulas: {tex: 'unavailable' for tex in formulas})
    monkeypatch.setattr('MaRDMO.checks.model.UNAVAILABLE', 'unavailable')
    html = preview(client, white)
    assert 'The TeX check of the MaRDI Portal did not answer' in html and f'{BUTTON} disabled' in html


def test_the_export_checks_again_and_names_what_changed(white, client):
    assert f'{BUTTON} />' in preview(client, white)
    without_description(white, 'formulation', 1)       # after the preview
    response = client.post(URL.format(white.pk), {})
    page = text(response.content.decode())
    assert 'Something changed since the preview' in page
    assert 'Formula (Page F2): Missing Short Description' in page
