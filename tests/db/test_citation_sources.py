'''The citation of a publication from each source MaRDMO asks (#138).

A publication that is neither on the MaRDI Portal nor on Wikidata gets its
citation from Crossref, DataCite, zbMATH or doi.org, and its authors' ORCID
iDs from ORCID.  One real answer per source was recorded (``citation_*``)
and is read by the source's parser; the same answers with parts removed
check what the parsers do when a source knows less.
'''
import copy
import json
from types import SimpleNamespace

import pytest

from MaRDMO.sources import citations
from MaRDMO.publication.models import Author, Publication

ATTENTION = '10.48550/arXiv.1706.03762'      # a preprint: DataCite, no journal
DIJKSTRA = '10.1007/BF01386390'              # zbMATH, with journal and year
SEG1D = '10.21105/joss.02404'                # a JOSS article: doi.org, ORCID


def response(body):
    '''A source's answer with *body* (as the parsers receive it).'''
    return SimpleNamespace(status_code=200, json=lambda: copy.deepcopy(body), text=json.dumps(body))


@pytest.fixture
def answers(portal):
    '''The recorded answers of all sources for the three publications.'''
    portal('citation_sources')
    return {
        'datacite': citations.get_datacite_data(ATTENTION).json(),
        'zbmath': citations.get_zbmath_data(DIJKSTRA).json(),
        'doi': citations.get_doi_data(SEG1D).json(),
        'orcid': citations.get_orcids(SEG1D).json(),
    }


def test_datacite(answers):
    publication = Publication.from_datacite(response(answers['datacite']))
    assert publication.title == 'Attention Is All You Need' and publication.date.startswith('2017')
    assert len(publication.authors) == 8 and publication.authors[0].label == 'Ashish Vaswani'
    # A preprint: no journal with a name (the parser gives an empty one; the lookup leaves it out)
    assert not any(journal.label for journal in publication.journal)


def test_zbmath(answers):
    publication = Publication.from_zbmath(response(answers['zbmath']))
    assert 'two problems in connexion with graphs' in publication.title and publication.date.startswith('1959')
    assert [author.label for author in publication.authors][0].endswith('Dijkstra')
    assert publication.authors[0].zbmath_id
    assert publication.journal and 'Numerische Mathematik' in publication.journal[0].label
    assert publication.volume == '1'


def test_doi_org(answers):
    publication = Publication.from_doi(response(answers['doi']))
    assert publication.title.startswith('seg1d') and publication.date.startswith('2020')
    assert publication.journal and publication.journal[0].label == 'Journal of Open Source Software'
    assert publication.authors


def test_orcid(answers):
    authors = [Author.from_orcid(entry) for entry in answers['orcid']['expanded-result']]
    assert authors and all(len(author.orcid_id) == 19 and author.orcid_id.count('-') == 3 for author in authors)
    assert all(author.label for author in authors)


# --- A source that knows less -------------------------------------------------------------------

def without(body, *path):
    '''*body* without the entry at *path* (keys and list indexes).'''
    body = copy.deepcopy(body)
    entry = body
    for key in path[:-1]:
        entry = entry[key]
    if isinstance(entry, list):
        del entry[path[-1]]
    else:
        entry.pop(path[-1], None)
    return body


def test_datacite_without_creators_and_dates(answers):
    body = without(without(answers['datacite'], 'data', 'attributes', 'creators'), 'data', 'attributes', 'dates')
    body = without(body, 'data', 'attributes', 'publicationYear')
    publication = Publication.from_datacite(response(body))
    assert publication.title == 'Attention Is All You Need'
    assert publication.authors == [] and not publication.date


def test_zbmath_without_source_and_authors(answers):
    body = copy.deepcopy(answers['zbmath'])
    for document in body['result']:
        document.pop('source', None)
        document.pop('contributors', None)
    publication = Publication.from_zbmath(response(body))
    assert 'two problems' in publication.title and publication.journal == [] and publication.authors == []


def test_doi_org_without_container(answers):
    publication = Publication.from_doi(response(without(answers['doi'], 'container-title')))
    # The journal keeps its ISSN, but has no name any more
    assert publication.title.startswith('seg1d') and not any(journal.label for journal in publication.journal)


@pytest.mark.parametrize('source', ['datacite', 'zbmath', 'doi'])
def test_an_empty_answer_has_no_title(answers, source):
    '''Without title the lookup lets the next source take over (utils._lookup_citation).'''
    empty = {'datacite': {'data': {'attributes': {}}}, 'zbmath': {'result': []}, 'doi': {}}[source]
    try:
        publication = getattr(Publication, f'from_{source}')(response(empty))
    except (KeyError, IndexError, TypeError, AttributeError):
        return                       # caught by the lookup, which goes on with the next source
    assert not publication.label
