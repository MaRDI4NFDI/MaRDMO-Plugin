'''The layout of a dropdown option: a source badge, the label in bold, the description below (#142).

It is the option's help, which RDMO renders as HTML in the open dropdown
only; the option's text stays "Label (Description)" (stored, shown in the
filled field, announced by screen readers).  A CSS rule in the help hides
the text of laid-out options.
'''
import re

import pytest

from MaRDMO.ids import NEW_DOI, NEW_ITEM, NOT_FOUND
from MaRDMO.components.dropdowns import option_help


def shown(help_html):
    '''``(badge, label, description)`` as the open dropdown shows them, without the CSS.'''
    body = re.sub(r'<style>.*?</style>', '', help_html, flags=re.S)
    texts = [text for text in re.split(r'<[^>]+>', body) if text]
    return tuple(texts) + ('',) * (3 - len(texts))


@pytest.mark.parametrize('identifier, badge', [
    ('mardi:Q1', 'mardi'), ('wikidata:Q2', 'wikidata'), ('user:6f1c', 'project'), (NOT_FOUND, 'new'),
    (f'{NEW_DOI}10.1000/x', 'new'),
])
def test_the_badge_names_the_source(identifier, badge):
    assert shown(option_help(identifier, 'alpha (first)')) == (badge, 'alpha', 'first')


def test_new_item_stays_plain():
    assert option_help(NOT_FOUND, NEW_ITEM) == ''


def test_an_option_without_source_has_no_help():
    assert option_help('', 'alpha') == '' and option_help('Q5', 'alpha (x)') == ''


@pytest.mark.parametrize('text, label, description', [
    ('reaction rate', 'reaction rate', ''),
    ('doi:10.1000/x', 'doi:10.1000/x', ''),
    ('Heat Equation (No Description Provided!)', 'Heat Equation', ''),
    ('Navier–Stokes (incompressible) (partial differential equation)', 'Navier–Stokes (incompressible)',
     'partial differential equation'),
])
def test_label_and_description(text, label, description):
    assert shown(option_help('mardi:Q1', text))[1:] == (label, description)


def test_labels_from_the_portal_are_escaped():
    layout = option_help('mardi:Q1', '<b>a & b</b> ("quoted" <x>)')
    assert '<b>' not in layout and '&lt;b&gt;a &amp; b&lt;/b&gt;' in layout and '&lt;x&gt;' in layout


def test_the_layout_hides_the_plain_text_of_its_option():
    layout = option_help('mardi:Q1', 'alpha (first)')
    assert layout.startswith('<style>') and '.interview-select-option:has(.mardmo-option)' in layout
    assert 'class="mardmo-option"' in layout
