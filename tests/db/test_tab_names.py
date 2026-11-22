'''The preview names pages by their tabs and links relations to them (#152).

white_2006 has quantity tabs QQK2..QQK14 (two were deleted before), so the
position of a page and its tab differ.
'''
import pytest

from MaRDMO.model.checks import ModelChecks
from MaRDMO.constants import BASE_URI
from MaRDMO.pages import PageRef
from tests.db.test_export import imported
from tests.support.html import element, links, rendered_preview, text


@pytest.fixture
def white(project, portal, monkeypatch):
    monkeypatch.setattr('MaRDMO.tex_check.check_formulas', lambda formulas: {})
    monkeypatch.setattr('MaRDMO.model.checks.check_formulas', lambda formulas: {})
    portal('export_white_2006')
    return imported(project, 'white_2006')


def tab(documentation, section, index):
    return documentation.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/{section}',
                                    set_prefix='', set_index=index)


def test_pages_are_headed_by_their_tab(white):
    answers, html = rendered_preview(white)
    assert answers['quantity'][1]['Tab'] == 'QQK2'
    assert text(element(html, id='page-quantity-1')).startswith('QQK2: total population size')
    assert 'QQK1:' not in text(html)


def test_relations_link_to_their_page(white):
    answers, html = rendered_preview(white)
    model = next(iter(answers['model'].values()))
    relatants = [entry['relatant'] for entry in model['RelationMF'].values()]
    assert all(isinstance(relatant, PageRef) for relatant in relatants)
    assert relatants[1].label == 'conservation law for the opiate-using career ODE model (F2)'
    assert ('conservation law for the opiate-using career ODE model', '#page-formulation-1') in links(html)
    assert 'conservation law for the opiate-using career ODE model (F2)' in text(html)
    # Every link to a page leads to a page of the preview
    targets = {href[1:] for _, href in links(html) if href.startswith('#page-')}
    assert targets and all(element(html, id=target) for target in targets)


def test_a_renamed_tab_is_named_everywhere(white):
    '''Heading, relations and checks use the tab name of the interview.'''
    renamed = tab(white, 'formulation', 1)
    renamed.text = 'conservation'
    renamed.save()
    answers, html = rendered_preview(white)
    assert text(element(html, id='page-formulation-1')).startswith('conservation: conservation law')
    assert 'conservation law for the opiate-using career ODE model (conservation)' in text(html)
    formula = answers['formulation'][1]
    formula.pop('Description')
    messages = ModelChecks().run(project=white, data=answers, catalog=str(white.catalog))
    assert any('(Page conservation)' in str(message) for message in messages)
