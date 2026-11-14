'''The preview names pages by their tabs and links relations to them (#152).

white_2006 has quantity tabs QQK2..QQK14 (two were deleted before), so the
position of a page and its tab differ.
'''
import re

import pytest
from django.template.loader import render_to_string

from MaRDMO import main
from MaRDMO.checks import Checks
from MaRDMO.constants import BASE_URI, CATALOG_TEMPLATE_MAP
from MaRDMO.pages import PageRef
from tests.db.test_export import imported


def preview(documentation):
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = documentation, None
    answers, options = provider.get_post_data()
    html = render_to_string(CATALOG_TEMPLATE_MAP['mardmo-model-catalog'],
                            {'answers': answers, 'option': options, 'title': 'x'})
    return answers, html


def text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


@pytest.fixture
def white(project, portal, monkeypatch):
    monkeypatch.setattr('MaRDMO.tex_check.check_formulas', lambda formulas: {})
    monkeypatch.setattr('MaRDMO.checks.model.check_formulas', lambda formulas: {})
    portal('export_white_2006')
    return imported(project, 'white_2006')


def tab(documentation, section, index):
    return documentation.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/{section}',
                                    set_prefix='', set_index=index)


def test_pages_are_headed_by_their_tab(white):
    answers, html = preview(white)
    assert answers['quantity'][1]['Tab'] == 'QQK2'
    assert re.search(r'<h2 id="page-quantity-1">\s*QQK2: total population size', html)
    assert 'QQK1:' not in text(html)


def test_relations_link_to_their_page(white):
    answers, html = preview(white)
    model = next(iter(answers['model'].values()))
    relatants = [entry['relatant'] for entry in model['RelationMF'].values()]
    assert all(isinstance(relatant, PageRef) for relatant in relatants)
    assert relatants[1].label == 'conservation law for the opiate-using career ODE model (F2)'
    assert '<a href="#page-formulation-1">conservation law for the opiate-using career ODE model</a> (F2)' in html
    anchors = set(re.findall(r'id="(page-[^"]+)"', html))
    links = re.findall(r'href="#(page-[^"]+)"', html)
    assert links and set(links) <= anchors


def test_a_renamed_tab_is_named_everywhere(white):
    '''Heading, relations and checks use the tab name of the interview.'''
    renamed = tab(white, 'formulation', 1)
    renamed.text = 'conservation'
    renamed.save()
    answers, html = preview(white)
    assert re.search(r'<h2 id="page-formulation-1">\s*conservation: conservation law', html)
    assert 'conservation law for the opiate-using career ODE model (conservation)' in text(html)
    formula = answers['formulation'][1]
    formula.pop('Description')
    messages = Checks().run_model(project=white, data=answers, catalog=str(white.catalog))
    assert any('(Page conservation)' in str(message) for message in messages)
