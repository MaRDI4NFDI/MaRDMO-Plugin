'''The preview shows the user's own items (``user:`` ID) as own items: no ID, and what they still need.'''
import re

from django.template.loader import render_to_string

from MaRDMO.checks import Checks
from MaRDMO.constants import CATALOG_MODEL, CATALOG_MODEL_BASICS
from MaRDMO.problems import attach

OWN = 'user:6f1c2a3e-0000-4000-8000-000000000000'


def text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def test_own_item_has_no_id_shown():
    html = text(render_to_string('MaRDMO/partials/_id.html', {'id': OWN, 'class': 'MODEL'}))
    assert 'ID : -' in html
    assert OWN not in html


def test_portal_item_shows_its_id():
    assert 'MaRDI Portal ID : Q1' in text(render_to_string('MaRDMO/partials/_id.html', {'id': 'mardi:Q1'}))


def checked(answers, *checks, catalog=CATALOG_MODEL):
    '''*answers* with the problems of the check methods *checks* attached, as the preview shows them.'''
    for section, pages in answers.items():
        for index, entry in pages.items():
            entry.setdefault('Tab', f'{section}{index + 1}')
            entry.setdefault('Anchor', f'page-{section}-{index}')
    runner = Checks()
    for check in checks:
        getattr(runner, check)(None, answers, catalog)
    return attach(answers, runner.err)


def test_own_publication_without_doi_is_marked():
    answers = checked({'publication': {0: {'ID': OWN, 'Name': 'p', 'Description': 'a paper'}}}, 'publication')
    html = render_to_string('MaRDMO/partials/_publication.html', {'values': answers['publication'][0], 'option': {}})
    assert 'Missing Publication DOI' in html


def test_own_formula_without_reference_is_marked_in_the_basics_catalog():
    answers = checked({'formulation': {0: {'ID': OWN, 'Name': 'f', 'Description': 'a formula'}}},
                      'formulation', catalog=CATALOG_MODEL_BASICS)
    html = render_to_string('MaRDMO/preview_model_basics.html', {'answers': answers, 'option': {}})
    assert 'Missing Reference' in html


def test_own_quantity_in_a_formula_has_no_id_shown():
    elements = {0: {'symbol': 'v', 'Info': {'Type': 'Quantity', 'Name': 'velocity', 'ID': OWN,
                                            'QKName': 'speed', 'QKID': 'not found', 'Description': 'a velocity'}}}
    html = render_to_string('MaRDMO/partials/_in_defining_formula.html', {'element': elements})
    assert OWN not in html


def test_own_page_with_the_name_and_description_of_an_earlier_one_is_marked():
    '''The export would make one item of them; the check says so on the page.'''
    answers = checked({'problem': {0: {'ID': 'user:1', 'Name': 'reaction rate', 'Description': 'a rate'},
                                   1: {'ID': 'user:2', 'Name': 'reaction rate', 'Description': 'another rate'},
                                   2: {'ID': 'user:3', 'Name': 'reaction rate', 'Description': 'a rate'},
                                   3: {'ID': 'mardi:Q1', 'Name': 'reaction rate', 'Description': 'a rate'}}},
                      'id_name_description')
    assert [entry.get('Problems') for entry in answers['problem'].values()] == \
        [None, None, {'Name': ['Same Name and Short Description as Page problem1']}, None]
    html = text(render_to_string('MaRDMO/partials/_name.html', {
        'values': answers['problem'][2], 'name': 'reaction rate'}))
    assert 'problem3: reaction rate' in html
    assert 'Same Name and Short Description as Page problem1' in html
