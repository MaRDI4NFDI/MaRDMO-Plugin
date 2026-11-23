'''The citation of a DOI, from the first source that knows it (#158).

The background lookup of a new publication and the preview ask the MaRDI
Portal and Wikidata first, then Crossref, DataCite, zbMATH and doi.org, and
complete the authors with ORCID; the first source that knows the
publication gives its citation (``best_citation``).  The answers of all
sources were recorded (``citation_lookup``).
'''
import pytest

from MaRDMO.components.publication.utils import get_citation
from MaRDMO.components.publication.worker import best_citation

DIJKSTRA = '10.1007/BF01386390'                 # on the portal and on Wikidata
SEG1D = '10.21105/JOSS.02404'                   # on Wikidata, not on the portal
NEW = '10.21105/JOSS.08200'                     # a JOSS article of 2025: only Crossref and doi.org
NOWHERE = '10.9999/MARDMO.TESTS.NOWHERE'


@pytest.fixture(autouse=True)
def recorded(portal):
    portal('citation_lookup')


def known(citations):
    return sorted(source for source, publication in citations.items() if publication and source != 'orcid')


def test_a_publication_on_the_portal():
    citations = get_citation(DIJKSTRA)
    # Both are asked at once; the portal's citation is the one used
    assert known(citations) == ['mardi', 'wikidata']
    assert best_citation(citations).id == 'mardi:Q78129'


def test_a_publication_on_wikidata():
    citations = get_citation(SEG1D)
    assert known(citations) == ['wikidata']
    assert best_citation(citations).id == 'wikidata:Q106245557'


def test_a_publication_only_crossref_and_doi_org_know():
    citations = get_citation(NEW)
    assert known(citations) == ['crossref', 'doi']
    citation = best_citation(citations)
    assert citation is citations['crossref'] and citation.title and citation.authors


def test_a_doi_no_source_knows():
    citations = get_citation(NOWHERE)
    assert known(citations) == [] and best_citation(citations) is None


def test_a_doi_with_a_quotation_mark_is_a_valid_sparql_string(monkeypatch):
    class Asked(Exception):
        pass
    queries = []

    def ask(sources):
        queries.extend(query for query, _, _ in sources.values())
        raise Asked
    monkeypatch.setattr('MaRDMO.components.publication.utils.query_sparql_pool', ask)
    with pytest.raises(Asked):
        get_citation('10.1000/A"B\\C')
    assert len(queries) == 2 and all('"10.1000/A\\"B\\\\C"' in query for query in queries)
