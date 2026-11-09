'''The preview shows the user's own items (``user:`` ID) as own items: no ID, and what they still need.'''
import re

from django.template.loader import render_to_string

OWN = 'user:6f1c2a3e-0000-4000-8000-000000000000'


def text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def test_own_item_has_no_id_shown():
    html = text(render_to_string('MaRDMO/partials/_id.html', {'id': OWN, 'class': 'MODEL'}))
    assert 'ID : -' in html
    assert OWN not in html


def test_portal_item_shows_its_id():
    assert 'MaRDI Portal ID : Q1' in text(render_to_string('MaRDMO/partials/_id.html', {'id': 'mardi:Q1'}))


def test_own_publication_without_doi_is_marked():
    html = render_to_string('MaRDMO/partials/_publication.html', {'values': {'ID': OWN}, 'option': {}})
    assert 'MISSING PUBLICATION DOI' in html


def test_own_formula_without_reference_is_marked_in_the_basics_catalog():
    answers = {'formulation': {0: {'ID': OWN, 'Name': 'f', 'Description': 'a formula'}}}
    html = render_to_string('MaRDMO/modelTemplate-basics.html', {'answers': answers, 'option': {}})
    assert 'MISSING FORMULA REFERENCE' in html


def test_own_quantity_in_a_formula_has_no_id_shown():
    elements = {0: {'symbol': 'v', 'Info': {'Type': 'Quantity', 'Name': 'velocity', 'ID': OWN,
                                            'QKName': 'speed', 'QKID': 'not found', 'Description': 'a velocity'}}}
    html = render_to_string('MaRDMO/partials/_in_defining_formula.html', {'element': elements})
    assert OWN not in html
