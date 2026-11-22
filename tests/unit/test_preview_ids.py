'''The preview shows the user's own items (``user:`` ID) as own items: no ID, and what they still need.'''
from django.template.loader import render_to_string

from MaRDMO.model.checks import ModelChecks
from MaRDMO.model.catalog import CATALOG_MODEL, CATALOG_MODEL_BASICS
from MaRDMO.problems import attach
from tests.support.html import text

OWN = 'user:6f1c2a3e-0000-4000-8000-000000000000'


def test_own_item_has_no_id_shown():
    html = text(render_to_string('MaRDMO/partials/_id.html', {'id': OWN, 'class': 'MODEL'}))
    assert 'ID: -' in html
    assert OWN not in html


def test_portal_item_shows_its_id():
    assert 'MaRDI Portal ID: Q1' in text(render_to_string('MaRDMO/partials/_id.html', {'id': 'mardi:Q1'}))


def checked(answers, *checks, catalog=CATALOG_MODEL):
    '''*answers* with the problems of the check methods *checks* attached, as the preview shows them.'''
    for section, pages in answers.items():
        for index, entry in pages.items():
            entry.setdefault('Tab', f'{section}{index + 1}')
            entry.setdefault('Anchor', f'page-{section}-{index}')
    runner = ModelChecks()
    for check in checks:
        getattr(runner, check)(None, answers, catalog)
    return attach(answers, runner.err)


def test_own_publication_without_doi_is_marked():
    answers = checked({'publication': {0: {'ID': OWN, 'Name': 'p', 'Description': 'a paper'}}}, 'publication')
    # At the ID, where the DOI is given (#158)
    html = render_to_string('MaRDMO/partials/_id.html', {'values': answers['publication'][0],
                                                         'id': answers['publication'][0]['ID']})
    assert 'Missing Publication DOI' in html
    assert 'Missing Publication DOI' not in render_to_string('MaRDMO/partials/_publication.html', {
        'values': answers['publication'][0], 'option': {}})


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


# --- New publications, selected by their DOI (#158) ----------------------------------------------

def new_publication(doi, **answers):
    from MaRDMO.getters import get_options  # noqa: PLC0415
    return {'ID': OWN, 'reference': {0: [get_options()['DOI'], doi]}, **answers}


def problems(entry):
    '''The problems of *entry*, without those of its relations (every publication needs one).'''
    return {field: [str(problem) for problem in found] for field, found in (entry.get('Problems') or {}).items()
            if not field.startswith('Relation')}


def test_a_new_publication_without_citation_is_marked_at_its_id():
    answers = checked({'publication': {0: new_publication('10.1000/x')}}, 'id_name_description', 'publication')
    # Its name and description come with the citation: no mark for them, the user cannot give them
    assert problems(answers['publication'][0]) == {
        'ID': ['No citation found for the DOI 10.1000/x: check the DOI, or open the preview again later']}
    heading = text(render_to_string('MaRDMO/preview_model_basics.html', {'answers': answers, 'option': {}}))
    assert 'doi:10.1000/x' in heading


def test_a_new_publication_with_citation_is_not_marked():
    answers = checked({'publication': {0: new_publication('10.1000/x', Name='seg1d', Description='scientific article')}},
                      'id_name_description', 'publication')
    assert problems(answers['publication'][0]) == {}


def test_an_invalid_doi_is_marked_at_the_id():
    answers = checked({'publication': {0: new_publication('11.1000/x', Name='p', Description='a paper')}},
                      'publication')
    assert list(problems(answers['publication'][0])) == ['ID']
    assert 'Invalid Publication DOI' in problems(answers['publication'][0])['ID'][0]


# --- Publications with the same name and description (#183) ---------------------------------------

def same_named(*pages):
    '''Publication pages ``{index: answers}`` named "Introduction" (scientific article), with *pages* ``(ID, DOI)``.'''
    from MaRDMO.pages import distinguish_publications, link_to_pages# noqa: PLC0415
    answers = {'publication': {index: new_publication(doi, ID=identifier, Name='Introduction',
                                                      Description='scientific article') if doi else
                               {'ID': identifier, 'Name': 'Introduction', 'Description': 'scientific article'}
                               for index, (identifier, doi) in enumerate(pages)},
               'model': {0: {'ID': 'user:model', 'Name': 'm', 'Description': 'a model',
                             'RelationP': {0: {'ID': 'user:second', 'Name': 'Introduction',
                                               'Description': 'scientific article'}}}}}
    return link_to_pages(distinguish_publications(answers))


def test_other_publications_with_the_same_name_get_their_doi_in_the_description():
    answers = same_named((OWN, '10.1000/a'), ('user:second', '10.1000/b'), ('wikidata:Q1', None))
    assert [page['Description'] for page in answers['publication'].values()] == [
        'scientific article', 'scientific article (DOI 10.1000/b)', 'scientific article (Wikidata QID Q1)']
    # Relations follow their page; the export makes three items of them
    assert answers['model'][0]['RelationP'][0]['Description'] == 'scientific article (DOI 10.1000/b)'
    from MaRDMO.ids import unique_items# noqa: PLC0415
    items, _ = unique_items({'publication': answers['publication']})
    assert len(items) == 3


def test_pages_of_one_publication_keep_their_description_and_are_marked():
    answers = same_named((OWN, '10.1000/a'), ('user:second', '10.1000/A'))
    assert {page['Description'] for page in answers['publication'].values()} == {'scientific article'}
    checked_answers = checked({'publication': answers['publication']}, 'id_name_description')
    assert problems(checked_answers['publication'][1]) == {
        'ID': ['Same Publication as Page publication1 (delete one of them)']}


def test_the_preview_says_why_a_description_has_its_doi():
    answers = same_named((OWN, '10.1000/a'), ('user:second', '10.1000/b'))
    html = text(render_to_string('MaRDMO/partials/_publication.html', {'values': answers['publication'][1],
                                                                       'option': {}}))
    assert 'another publication of this documentation has the same title and description' in html
