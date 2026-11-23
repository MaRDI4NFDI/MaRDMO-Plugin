'''The preview looks up only the citations new and Wikidata publications are missing, and changes no ID (#158).

A new publication (``user:`` ID) gets its citation in the background when it
is selected; the preview looks it up for one whose lookup failed, for those
of imported projects, and for Wikidata publications (the export creates
them with their citation).  Publications of the MaRDI Portal are left as
they are.  Before, the preview switched a Wikidata publication to the
portal item, and a new one to the item of a source that knew its DOI.  The
citations of the sources are given.
'''
import pytest

from MaRDMO.core.constants import BASE_URI
from MaRDMO.core.config import get_options
from MaRDMO.writes import value_editor
from MaRDMO.publication import worker
from MaRDMO.publication.models import Publication
from MaRDMO.publication.worker import PublicationRetriever

OWN = 'user:6f1c2a3e-0000-4000-8000-000000000000'
SEG1D = Publication(id='wikidata:Q106245557', label='seg1d', description='scientific article published in 2020',
                    title='seg1d: A Python package for automated segmentation')


@pytest.fixture
def looked_up(monkeypatch):
    '''The DOIs looked up; every source but Wikidata knows nothing.'''
    dois = []

    def get_citation(doi):
        dois.append(doi)
        return {'wikidata': SEG1D}
    monkeypatch.setattr(worker, 'get_citation', get_citation)
    return dois


def page(project, set_index, external_id, text, doi=None, name=None, title=None):
    '''A publication page and its answers: ``{'ID': …, 'reference': …, 'Name': …, 'title': …}``.'''
    value_editor(project=project, uri=f'{BASE_URI}domain/publication',
                 info={'text': f'P{set_index + 1}', 'set_index': set_index})
    value_editor(project=project, uri=f'{BASE_URI}domain/publication/id',
                 info={'text': text, 'external_id': external_id, 'set_index': set_index})
    entry = {'ID': external_id}
    if doi:
        value_editor(project=project, uri=f'{BASE_URI}domain/publication/reference',
                     info={'option': get_options()['DOI'], 'text': doi, 'set_index': set_index})
        entry['reference'] = {0: [get_options()['DOI'], doi]}
    if name:
        value_editor(project=project, uri=f'{BASE_URI}domain/publication/name',
                     info={'text': name, 'set_index': set_index})
        entry['Name'] = name
    if title:
        value_editor(project=project, uri=f'{BASE_URI}domain/publication/title',
                     info={'text': title, 'set_index': set_index})
        entry['title'] = title
    return entry


def answer(project, path, set_index=0):
    return list(project.values.filter(attribute__uri=f'{BASE_URI}domain/publication/{path}', set_index=set_index)
                .values_list('external_id' if path == 'id' else 'text', flat=True))


def test_a_new_publication_without_citation_gets_it_and_keeps_its_id(project, looked_up):
    documentation = project('mardmo-model-catalog')
    answers = {'publication': {0: page(documentation, 0, OWN, 'doi:10.21105/joss.02404', doi='10.21105/joss.02404')}}
    PublicationRetriever().get_information(documentation, None, answers)
    assert looked_up == ['10.21105/JOSS.02404']
    assert answer(documentation, 'name') == ['seg1d']
    assert answer(documentation, 'title') == ['seg1d: A Python package for automated segmentation']
    # Not switched to the Wikidata item that knew the DOI
    assert answer(documentation, 'id') == [OWN]


def test_a_publication_with_its_citation_is_not_looked_up_again(project, looked_up):
    documentation = project('mardmo-model-catalog')
    answers = {'publication': {0: page(documentation, 0, OWN, 'doi:10.1000/x', doi='10.1000/x', name='mine',
                                       title='mine')}}
    PublicationRetriever().get_information(documentation, None, answers)
    assert looked_up == [] and answer(documentation, 'name') == ['mine']


def test_a_wikidata_publication_gets_its_citation_and_a_portal_one_none(project, looked_up):
    documentation = project('mardmo-model-catalog')
    answers = {'publication': {
        0: page(documentation, 0, 'wikidata:Q106245557', 'seg1d (scientific article)', doi='10.21105/JOSS.02404',
                name='seg1d'),
        1: page(documentation, 1, 'mardi:Q78129', 'A note on two problems (scientific article)', doi='10.1007/BF01386390'),
    }}
    PublicationRetriever().get_information(documentation, None, answers)
    assert looked_up == ['10.21105/JOSS.02404']
    assert answer(documentation, 'title', 0) == ['seg1d: A Python package for automated segmentation']
    # No ID changes: the Wikidata publication stays one (the preview's box offers the portal item, if any)
    assert answer(documentation, 'id', 0) == ['wikidata:Q106245557'] and answer(documentation, 'id', 1) == ['mardi:Q78129']


def test_a_doi_no_source_knows_leaves_the_publication_without_citation(project, monkeypatch):
    monkeypatch.setattr(worker, 'get_citation', lambda doi: {'crossref': None})
    documentation = project('mardmo-model-catalog')
    answers = {'publication': {0: page(documentation, 0, OWN, 'doi:10.1000/x', doi='10.1000/x')}}
    PublicationRetriever().get_information(documentation, None, answers)
    assert answer(documentation, 'name') == [] and answer(documentation, 'id') == [OWN]
