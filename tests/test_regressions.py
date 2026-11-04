'''One test per fix of the 0.7.0 review that the unit tests do not cover already.

Covered elsewhere: qualifier merge and PATCH of partial statements
(unit/test_merge_qualifiers.py, unit/test_export_requests.py), results page
"qualifiers added" (unit/test_export_requests.py), publication matching by
identifiers, preprints and formatting tags (unit/test_publication.py),
"manifests" relation and placeholders of the queries (static/).
'''
from pathlib import Path

import pytest

import MaRDMO.queries as queries
from MaRDMO.getters import get_items, get_mathmoddb, get_properties
from MaRDMO.model.models import MathematicalModel
from MaRDMO.payload import GeneratePayload
from MaRDMO.templatetags.mardmo_tags import publication_info

PACKAGE = Path(__file__).parents[1] / 'MaRDMO'


# --- Search: a Wikidata item with the label and description of a MaRDI item is offered once

@pytest.fixture
def search_results(monkeypatch):
    results = {
        'mardi': [{'id': 'mardi:Q1', 'text': 'Navier-Stokes Equation (partial differential equation) [mardi]'},
                  {'id': 'mardi:Q2', 'text': 'Heat Equation (No Description Provided!) [mardi]'}],
        'wikidata': [
            {'id': 'Q100', 'display': {'label': {'value': 'navier-stokes equation'},
                                       'description': {'value': 'partial differential equation'}}},
            {'id': 'Q101', 'display': {'label': {'value': 'Navier-Stokes equation'},
                                       'description': {'value': 'in fluid dynamics'}}},
            {'id': 'Q102', 'display': {'label': {'value': 'Heat Equation'}}},
        ],
    }
    monkeypatch.setattr(queries, '_cached_search', lambda source, search, item_class, func: results[source])


def test_wikidata_duplicate_of_a_mardi_item_is_left_out(search_results):
    ids = {option['id'] for option in queries.query_sources('Navier-Stokes', not_found=False)}
    assert ids == {'mardi:Q1', 'mardi:Q2', 'wikidata:Q101', 'wikidata:Q102'}


def test_label_without_description_does_not_make_items_the_same(search_results):
    '''"Heat Equation" without description on both sides: both are offered.'''
    ids = {option['id'] for option in queries.query_sources('Heat', not_found=False)}
    assert {'mardi:Q2', 'wikidata:Q102'} <= ids


# --- Model: imported properties are numbered without gaps

def test_model_properties_are_numbered_from_zero():
    '''Only the properties that are true get a line; before, the line was the position in the full list.'''
    data = {'is_static': {'value': 'True'}, 'is_linear': {'value': 'False'}, 'is_stochastic': {'value': 'True'}}
    model = MathematicalModel.from_query_single(data)
    mathmoddb = get_mathmoddb()
    assert model.properties == {0: [mathmoddb.get(key='is_static')['url']],
                                1: [mathmoddb.get(key='is_stochastic')['url']]}


# --- Export: new authors and journals

@pytest.fixture
def new_publication_items():
    payload = GeneratePayload(
        url='https://portal.example.org',
        user_items={
            'Item0000000001': {'ID': 'no journal found', 'Name': 'New Journal', 'Description': 'scientific journal',
                               'issn': '1234-5678'},
            'Item0000000002': {'ID': 'no author found', 'Name': 'A. Author', 'Description': 'scientist',
                               'orcid': '0000-0001-0000-0001', 'zbmath': ''},
        },
        wikibase={'items': get_items(), 'properties': get_properties(), 'relations': {}},
        dependency={'Item0000000001': set(), 'Item0000000002': set()},
    )
    # No duplicate search on the portal: neither item exists there
    payload._check_duplicates = lambda items: None
    payload._duplicates = {('New Journal', 'scientific journal'): None, ('A. Author', 'scientist'): None}
    payload.process_items()
    return payload.state.dictionary


def test_new_journal_and_author_are_grouped_by_their_class(new_publication_items):
    '''The success page listed a new author under "Journal".'''
    assert new_publication_items['Item0000000001']['class'] == 'Journal'
    assert new_publication_items['Item0000000002']['class'] == 'Author'


def test_new_journal_gets_the_journal_profile(new_publication_items):
    properties, items = get_properties(), get_items()
    statements = new_publication_items['Item0000000001']['statements']
    assert [properties['MaRDI profile type'], 'wikibase-item', items['MaRDI journal profile']] in statements
    assert [properties['ISSN'], 'external-id', '1234-5678'] in statements


# --- Workflow: data sets are found by DOI only

@pytest.mark.parametrize('name', ['data_set_mardi.sparql', 'data_set_wikidata.sparql'])
def test_data_sets_are_looked_up_by_doi_only(name):
    '''Hydration fell back to the URL, which then sat in the DOI field and blocked the export.'''
    query = (PACKAGE / 'workflow' / 'queries' / name).read_text(encoding='utf-8')
    assert '?DOI' in query
    assert '?URL' not in query


# --- Model: research field relatants

def test_research_field_relatant_prefix_is_ad():
    '''Research fields are academic disciplines: "AD", not "RF".'''
    from MaRDMO.constants import BASE_URI
    from MaRDMO.getters import get_questions
    from MaRDMO.model.constants import get_uri_prefix_map
    questions = get_questions('model')
    assert get_uri_prefix_map()[f'{BASE_URI}{questions["Research Problem"]["RFRelatant"]["uri"]}']['prefix'] == 'AD'


# --- Preview of a publication

def test_publication_info_counts_what_the_export_creates():
    values = {
        'ID': 'not found',
        'title': 'A Title',
        'date': '2020-05-01',
        'volume': '5', 'issue': '2', 'page': '1-10',
        'author': {
            0: {'Name': 'On Portal', 'ID': 'mardi:Q1'},
            1: {'Name': 'With ORCID', 'ID': 'no author found', 'orcid': '0000-0001'},
            2: {'Name': 'Name Only', 'ID': 'no author found'},
            3: {'Name': 'Fourth', 'ID': 'wikidata:Q5'},
        },
        'journal': {0: {'Name': 'New Journal', 'ID': 'no journal found', 'issn': '1234-5678'}},
    }
    info = publication_info(values)
    assert info['new'] == ['publication', 'journal', '2 authors']
    assert info['name_only'] == 1
    assert [a['status'] for a in info['authors']] == ['portal', 'new', 'name only', 'new']
    assert info['authors'][3]['wikidata'] == 'Q5'
    assert str(info['citation']) == ('On Portal, With ORCID, Name Only et al. (2020). A Title. '
                                     '<em>New Journal</em> 5(2), 1-10.')


def test_publication_info_escapes_fetched_text():
    info = publication_info({'title': '<script>x</script>', 'author': {}, 'journal': {}})
    assert '<script>' not in str(info['citation'])


def test_publication_on_the_portal_creates_nothing():
    info = publication_info({'ID': 'mardi:Q7', 'title': 'T', 'author': {0: {'Name': 'A', 'ID': 'mardi:Q1'}}})
    assert (info['on_portal'], info['new']) == (True, [])


# --- Search results deduplication needs the description

def test_label_description_ignores_options_without_description():
    assert queries._label_description({'text': 'Heat (No Description Provided!) [wikidata]'}) is None
    assert queries._label_description({'text': 'Heat Equation (a PDE) [mardi]'}) == ('heat equation', 'a PDE')


def test_publication_name_is_stored_as_label():
    from MaRDMO.publication.constants import ITEMINFOS
    assert ITEMINFOS['Name'] == 'label'

