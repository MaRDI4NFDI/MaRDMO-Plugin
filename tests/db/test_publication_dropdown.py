'''The publication dropdown: a publication is selected by its identifier (#158).

The user types the identifier with its prefix (for now ``doi:10.…``); a
title finds nothing.  A publication on the MaRDI Portal is offered as the
portal item only, one only on Wikidata as the Wikidata item, one found
nowhere as the identifier itself (a new publication, tagged "new").  An
identifier that is not valid is offered without asking anyone: saving it is
refused with the reason.  The searches of the portal and Wikidata were
recorded (``publication_dropdown``); the dropdown is asked through RDMO's
options API, as the interview does.
'''
import pytest
from rdmo.options.models import OptionSet
from rdmo.projects.models import Membership

from MaRDMO.ids import option_help, publication_doi

DIJKSTRA = '10.1007/BF01386390'           # on the portal (Q78129) and on Wikidata (Q21694527)
SEG1D = '10.21105/joss.02404'             # only on Wikidata (Q106245557)
NOWHERE = '10.9999/mardmo.tests.nowhere'
# On the portal (Q4608560) with "<" and ">" percent-encoded, as imported
LORENZ = '10.1175/1520-0469(1963)020<0130:DNF>2.0.CO;2'


@pytest.mark.parametrize('typed, doi', [
    (f'doi:{DIJKSTRA}', DIJKSTRA),
    (f'  DOI: {DIJKSTRA} ', DIJKSTRA),
    (f'doi:https://doi.org/{DIJKSTRA}', DIJKSTRA),
    (f'doi: http://dx.doi.org/{DIJKSTRA}', DIJKSTRA),
    # A link is percent-encoded: its DOI is decoded
    ('doi:https://doi.org/10.1175/1520-0469(1963)020%3C0130:DNF%3E2.0.CO;2', LORENZ),
    ('doi:', ''),
    (DIJKSTRA, None),                                  # no prefix
    (f'https://doi.org/{DIJKSTRA}', None),
    ('A note on two problems in connexion with graphs', None),
    ('zbmath:0092.16002', None),                       # not yet
])
def test_the_doi_of_what_is_typed(typed, doi):
    assert publication_doi(typed) == doi


@pytest.fixture
def options(project, client, django_user_model, portal):
    '''The options of the publication dropdown for a text, as the interview asks for them.'''
    portal('publication_dropdown')
    user = django_user_model.objects.create_user('owner', password='owner')
    client.force_login(user)
    documentation = project('mardmo-model-catalog')
    Membership.objects.create(project=documentation, user=user, role='owner')
    optionset = OptionSet.objects.get(provider_key='Publication')

    def ask(text):
        response = client.get(f'/api/v1/projects/projects/{documentation.pk}/options/',
                              {'optionset': optionset.pk, 'search': text})
        assert response.status_code == 200
        return [(option['id'], option['text'], option.get('help', '')) for option in response.json()]
    return ask


def test_a_publication_on_the_portal_is_offered_as_the_portal_item_only(options):
    found = options(f'doi:{DIJKSTRA}')
    assert [(identifier, '>mardi<' in tag) for identifier, _, tag in found] == [('mardi:Q78129', True)]
    assert 'two problems in connexion with graphs' in found[0][1]


def test_a_publication_only_on_wikidata_is_the_wikidata_item(options):
    (identifier, text, tag), = options(f'doi:{SEG1D}')
    assert identifier == 'wikidata:Q106245557' and '>wikidata<' in tag and text.startswith('seg1d')


def test_a_publication_found_nowhere_is_new(options):
    assert options(f'doi:{NOWHERE}') == [(f'new:doi:{NOWHERE}', f'doi:{NOWHERE}', option_help('new:doi:', f'doi:{NOWHERE}'))]


def test_the_case_of_a_doi_does_not_matter(options):
    assert [identifier for identifier, _, _ in options(f'doi:{DIJKSTRA.lower()}')] == ['mardi:Q78129']


def test_an_invalid_doi_is_offered_without_a_search(options, monkeypatch):
    monkeypatch.setattr('MaRDMO.queries.find_publications', lambda doi: pytest.fail('searched'))
    assert options('doi:11.1000/x') == [('new:doi:11.1000/x', 'doi:11.1000/x', option_help('new:doi:', 'doi:11.1000/x'))]


@pytest.mark.parametrize('typed', [DIJKSTRA, 'A note on two problems', 'doi:'])
def test_no_identifier_no_options(options, typed):
    assert options(typed) == []


def test_a_doi_the_portal_has_percent_encoded_is_the_portal_item(options):
    assert [identifier for identifier, _, _ in options(f'doi:{LORENZ}')] == ['mardi:Q4608560']


def test_the_forms_of_a_doi_on_the_portal():
    from MaRDMO.queries import portal_doi_forms  # noqa: PLC0415
    assert portal_doi_forms(DIJKSTRA) == [DIJKSTRA]
    assert portal_doi_forms(LORENZ) == [LORENZ, '10.1175/1520-0469(1963)020%3C0130:DNF%3E2.0.CO;2']
    # The check character of old DOIs
    assert portal_doi_forms('10.1002/(SICI)1097-4636(199907)46:1<1::AID-JBM1>3.0.CO;2-#')[1] == (
        '10.1002/(SICI)1097-4636(199907)46:1%3C1::AID-JBM1%3E3.0.CO;2-%23')
