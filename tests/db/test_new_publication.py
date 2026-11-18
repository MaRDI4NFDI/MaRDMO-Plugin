'''A new publication, selected by its DOI: saved at once, its citation looked up in the background (#158).

The interview saves ``doi:10.…`` (the option ``new:doi:10.…``): the page
gets a ``user:`` ID and the DOI, and once these are committed a thread looks
up the citation and writes it into the publication's hidden answers.  An
invalid DOI is refused when it is saved.  The sources' answers are given.
'''
import threading
from types import SimpleNamespace

import pytest
from rdmo.domain.models import Attribute
from rdmo.projects.models import Membership, Value

from MaRDMO.constants import BASE_URI
from MaRDMO.ids import is_user_id
from MaRDMO.publication import handlers
from MaRDMO.publication.models import Author, Journal, Publication

DOI = '10.21105/joss.02404'
SEG1D = Publication(label='seg1d', description='scientific article published in 2020',
                    title='seg1d: A Python package for automated segmentation', date='2020-08-12',
                    journal=[Journal(id=None, issn='2475-9066', label='Journal of Open Source Software', description='')],
                    authors=[Author(id=None, label='Mathieu Bourgeois', description='', orcid_id='0000-0002-1825-0097',
                                    zbmath_id=None, wikidata_id=None)])


def answers(documentation, path, set_index=0):
    return list(documentation.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/{path}',
                                            set_index=set_index).values_list('text', flat=True))


@pytest.fixture
def interview(project, client, django_user_model):
    '''Save the publication page as the interview does: through RDMO's value API.'''
    user = django_user_model.objects.create_user('owner', password='owner')
    client.force_login(user)
    documentation = project('mardmo-model-catalog')
    Membership.objects.create(project=documentation, user=user, role='owner')

    def post(path, text, external_id='', set_index=0, set_prefix=''):
        return client.post(f'/api/v1/projects/projects/{documentation.pk}/values/', {
            'attribute': Attribute.objects.get(uri=f'{BASE_URI}domain/{path}').pk, 'set_prefix': set_prefix,
            'set_index': set_index, 'collection_index': 0, 'text': text, 'external_id': external_id,
            'value_type': 'text'}, content_type='application/json')
    post('publication', 'P1')
    return documentation, post


@pytest.fixture
def started(monkeypatch):
    '''The lookups the handler starts, not run: ``[(project ID, set index, item ID, DOI)]``.

    The test's transaction is never committed: what waits for the commit runs at once.
    '''
    lookups = []
    monkeypatch.setattr(handlers.transaction, 'on_commit', lambda callback, *args, **kwargs: callback())
    monkeypatch.setattr(handlers, 'start_lookup', lambda *args: lookups.append(args))
    return lookups


def test_a_new_publication_is_saved_with_its_doi(interview, started):
    documentation, post = interview
    response = post('publication/id', f'doi:{DOI}', f'new:doi:{DOI}')
    assert response.status_code == 201
    saved = response.json()
    assert is_user_id(saved['external_id']) and saved['text'] == f'doi:{DOI}'
    # The DOI is the publication's reference (hidden): checks and export read it
    assert answers(documentation, 'publication/reference') == [DOI]
    assert started == [(documentation.pk, 0, saved['external_id'], DOI)]


def test_an_invalid_doi_is_refused_and_nothing_happens(interview, started):
    documentation, post = interview
    response = post('publication/id', 'doi:11.1000/x', 'new:doi:11.1000/x')
    assert response.status_code == 400
    assert 'Invalid DOI' in str(response.json())
    assert answers(documentation, 'publication/id') == [] and started == []


def test_a_publication_of_the_portal_is_filled_from_there(interview, started, monkeypatch):
    documentation, post = interview
    filled = []
    monkeypatch.setattr(handlers.Information, 'fill_citations',
                        lambda self, project, entries, catalog='', snapshot=None: filled.extend(entries))
    post('publication/id', 'A note on two problems (scientific article)', 'mardi:Q78129')
    assert [entry[1] for entry in filled] == ['mardi:Q78129'] and started == []


def test_another_doi_replaces_the_publication_on_the_page(interview, started):
    documentation, post = interview
    first = post('publication/id', f'doi:{DOI}', f'new:doi:{DOI}').json()
    response = client_put(documentation, post, first, '10.1000/other')
    assert answers(documentation, 'publication/reference') == ['10.1000/other']
    # The page keeps its own ID (as "new item" again would)
    assert response['external_id'] == first['external_id'] and started[-1][3] == '10.1000/other'


def client_put(documentation, post, saved, doi):
    '''Change the saved ID answer to another DOI, as the interview does.'''
    from django.test import Client  # noqa: PLC0415 (a second client of the same user)
    client = Client()
    client.force_login(documentation.memberships.get(role='owner').user)
    return client.put(f'/api/v1/projects/projects/{documentation.pk}/values/{saved["id"]}/',
                      {**saved, 'text': f'doi:{doi}', 'external_id': f'new:doi:{doi}'},
                      content_type='application/json').json()


# --- The lookup ---------------------------------------------------------------------------------

@pytest.fixture
def lookup(monkeypatch):
    '''Run the lookup in the test's thread, keeping the test's database connection.'''
    monkeypatch.setattr(handlers, 'connection', SimpleNamespace(close=lambda: None))
    sources = {'crossref': SEG1D}
    monkeypatch.setattr(handlers, 'get_citation', lambda doi: {**{source: None for source in (
        'mardi', 'wikidata', 'crossref', 'datacite', 'zbmath', 'doi')}, **sources})
    return sources


def test_the_lookup_writes_the_citation(interview, started, lookup):
    documentation, post = interview
    saved = post('publication/id', f'doi:{DOI}', f'new:doi:{DOI}').json()
    handlers.lookup_publication(*started[0])
    assert answers(documentation, 'publication/name') == ['seg1d']
    assert answers(documentation, 'publication/title') == ['seg1d: A Python package for automated segmentation']
    assert answers(documentation, 'publication/journal/name') == ['Journal of Open Source Software']
    assert answers(documentation, 'publication/author/orcid') == ['0000-0002-1825-0097']
    # Neither the ID answer nor the DOI changed
    assert documentation.values.get(pk=saved['id']).text == f'doi:{DOI}'
    assert answers(documentation, 'publication/reference') == [DOI]


def test_the_lookup_does_not_write_on_a_changed_page(interview, started, lookup):
    documentation, post = interview
    post('publication/id', f'doi:{DOI}', f'new:doi:{DOI}')
    documentation.values.filter(attribute__uri=f'{BASE_URI}domain/publication/id').update(external_id='mardi:Q1')
    handlers.lookup_publication(*started[0])
    assert answers(documentation, 'publication/name') == []


def test_a_publication_no_source_knows_gets_no_citation(interview, started, lookup):
    documentation, post = interview
    lookup.clear()
    post('publication/id', f'doi:{DOI}', f'new:doi:{DOI}')
    handlers.lookup_publication(*started[0])
    assert answers(documentation, 'publication/name') == [] and answers(documentation, 'publication/reference') == [DOI]


def test_an_error_of_the_lookup_is_logged(interview, started, monkeypatch, caplog):
    documentation, post = interview
    monkeypatch.setattr(handlers, 'connection', SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(handlers, 'get_citation', lambda doi: 1 / 0)
    post('publication/id', f'doi:{DOI}', f'new:doi:{DOI}')
    handlers.lookup_publication(*started[0])
    assert 'Could not look up the publication' in caplog.text


# --- In the background, with real commits -------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_the_lookup_runs_in_the_background_after_the_commit(project, client, django_user_model, monkeypatch):
    threads = []

    class Thread(threading.Thread):
        def start(self):
            threads.append(self)
            super().start()
    monkeypatch.setattr(handlers.threading, 'Thread', Thread)
    monkeypatch.setattr(handlers, 'get_citation', lambda doi: {'crossref': SEG1D})
    user = django_user_model.objects.create_user('owner', password='owner')
    client.force_login(user)
    documentation = project('mardmo-model-catalog')
    Membership.objects.create(project=documentation, user=user, role='owner')
    for path, text, external_id, set_prefix in [('publication', 'P1', '', ''),
                                                ('publication/id', f'doi:{DOI}', f'new:doi:{DOI}', '')]:
        client.post(f'/api/v1/projects/projects/{documentation.pk}/values/', {
            'attribute': Attribute.objects.get(uri=f'{BASE_URI}domain/{path}').pk, 'set_prefix': set_prefix,
            'set_index': 0, 'collection_index': 0, 'text': text, 'external_id': external_id,
            'value_type': 'text'}, content_type='application/json')
    thread, = threads
    thread.join(10)
    assert not thread.is_alive()
    assert answers(documentation, 'publication/title') == ['seg1d: A Python package for automated segmentation']
    assert Value.objects.filter(project=documentation, attribute__uri=f'{BASE_URI}domain/publication/reference',
                                text=DOI).exists()
