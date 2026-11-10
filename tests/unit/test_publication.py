'''Publication metadata: matching authors and journals, cleaning fetched text.'''
import pytest

from MaRDMO.ids import is_user_id, part_id
from MaRDMO.publication.models import Author, Journal, Publication
from MaRDMO.publication.utils import _identifiers, assign_id
from MaRDMO.publication.worker import _single_line


def author(id=None, label='A. Author', orcid=None, zbmath=None, wikidata=None):
    return Author(id=id, label=label, description='scientist', orcid_id=orcid, zbmath_id=zbmath, wikidata_id=wikidata)


def journal(id=None, label='Journal', issn=None, wikidata=None):
    return Journal(id=id, issn=issn, label=label, description='scientific journal', wikidata_id=wikidata)


# --- _identifiers

def test_identifiers_of_an_author():
    assert _identifiers(author(orcid='0000-0001', zbmath='doe.john', wikidata='Q5')) == {
        ('orcid', '0000-0001'), ('zbmath', 'doe.john'), ('wikidata', 'Q5')}


def test_none_text_is_no_identifier():
    '''Some portal authors carry the text "None" as zbMATH ID.'''
    assert _identifiers(author(zbmath='None')) == set()


def test_wikidata_qid_from_the_id_of_a_wikidata_entity():
    assert _identifiers(author(id='wikidata:Q7')) == {('wikidata', 'Q7')}


def test_issn_is_compared_in_upper_case():
    assert _identifiers(journal(issn='1234-567x')) == {('issn', '1234-567X')}


# --- assign_id

def test_author_gets_the_portal_item_with_the_same_orcid():
    entity = author(orcid='0000-0001')
    assign_id([entity], {'0': author(id='Q1', label='Portal Name', orcid='0000-0001')}, {})
    assert (entity.id, entity.label) == ('mardi:Q1', 'Portal Name')


def test_portal_is_preferred_over_wikidata():
    entity = author(orcid='0000-0001')
    assign_id([entity],
              {'0': author(id='Q1', orcid='0000-0001')},
              {'0': author(id='Q100', orcid='0000-0001')})
    assert entity.id == 'mardi:Q1'


def test_wikidata_item_leads_to_the_portal_item_holding_its_qid():
    '''ORCID -> Wikidata item Q100 -> portal item with Wikidata QID Q100 (P12).'''
    entity = author(orcid='0000-0001')
    assign_id([entity],
              {'0': author(id='Q1', wikidata='Q100')},
              {'0': author(id='Q100', orcid='0000-0001')})
    assert entity.id == 'mardi:Q1'


def test_wikidata_item_when_the_portal_has_none():
    entity = author(orcid='0000-0001')
    assign_id([entity], {}, {'0': author(id='Q100', label='Wikidata Name', orcid='0000-0001')})
    assert (entity.id, entity.label) == ('wikidata:Q100', 'Wikidata Name')


def test_author_without_identifier_stays_a_name():
    '''Names are never compared: "A. Author" does not become the portal's "A. Author".'''
    entity = author()
    assign_id([entity], {'0': author(id='Q1')}, {'0': author(id='Q100')})
    assert (entity.id, entity.label) == (part_id('author', 'A. Author'), 'A. Author')


def test_none_zbmath_ids_do_not_match():
    entity = author(zbmath='None')
    assign_id([entity], {'0': author(id='Q1', zbmath='None')}, {})
    assert entity.id == part_id('author', 'A. Author')


def test_orcid_decides_over_zbmath():
    entity = author(orcid='0000-0001', zbmath='doe.john')
    assign_id([entity],
              {'0': author(id='Q1', zbmath='doe.john'), '1': author(id='Q2', orcid='0000-0001')},
              {})
    assert entity.id == 'mardi:Q2'


def test_an_item_is_not_given_to_two_authors():
    first, second = author(label='First', orcid='0000-0001'), author(label='Second', zbmath='doe.john')
    assign_id([first, second], {'0': author(id='Q1', orcid='0000-0001', zbmath='doe.john')}, {})
    assert (first.id, second.id) == ('mardi:Q1', part_id('author', 'doe.john'))


def test_portal_entities_are_left_alone():
    entity = author(id='mardi:Q9', orcid='0000-0001')
    assign_id([entity], {'0': author(id='Q1', orcid='0000-0001')}, {})
    assert entity.id == 'mardi:Q9'


def test_journal_by_issn():
    entity = journal(issn='1234-567x')
    assign_id([entity], {'0': journal(id='Q3', label='Portal Journal', issn='1234-567X')}, {})
    assert (entity.id, entity.label) == ('mardi:Q3', 'Portal Journal')


def test_journal_by_the_wikidata_qid_of_the_portal_journal():
    '''journal.sparql returns the Wikidata QID of portal journals.'''
    entity = journal(issn='1234-5678')
    assign_id([entity],
              {'0': journal(id='Q3', wikidata='Q300')},
              {'0': journal(id='Q300', issn='1234-5678')})
    assert entity.id == 'mardi:Q3'


# --- parsing query results

def test_journal_from_query_with_wikidata_qid():
    entity = Journal.from_query('Q3 <|> Journal <|>  <|> 1234-5678 <|> Q300')
    assert (entity.description, entity.issn, entity.wikidata_id) == (
        'scientific journal (ISSN 1234-5678)', '1234-5678', 'Q300')


def test_author_from_query_without_id_is_new():
    entity = Author.from_query(' <|> A. Author <|>  <|> 0000-0001 <|>  <|> ')
    assert (entity.id, entity.description) == (part_id('author', '0000-0001'), 'scientist (ORCID iD 0000-0001)')


def test_new_authors_and_journals_get_the_same_id_each_time():
    '''The preview writes them again each time (#118): the ID comes from their first identifier.'''
    assert is_user_id(author(orcid='0000-0001').id)
    assert author(orcid='0000-0001', label='Other Name').id == author(orcid='0000-0001').id
    assert author(zbmath='doe.john').id != author(orcid='0000-0001').id
    assert journal(issn='1234-5678').id == part_id('journal', '1234-5678')
    assert journal(label='No ISSN').id == part_id('journal', 'No ISSN')
    assert author(id='mardi:Q1').id == 'mardi:Q1'


# --- fetched text

@pytest.mark.parametrize('text, expected', [
    ('Line\n  break', 'Line break'),
    ('<i>Escherichia coli</i> in H<sub>2</sub>O', 'Escherichia coli in H2O'),
    ('Fish &amp; Chips', 'Fish & Chips'),
    ('<jats:title>Title</jats:title>', 'Title'),
    ('<mml:math><mml:mi>x</mml:mi></mml:math>', 'x'),
    ('a < b and c > d', 'a < b and c > d'),
    (None, None),
])
def test_single_line(text, expected):
    assert _single_line(text) == expected


# --- Crossref

class Response:
    def __init__(self, message):
        self.message = message

    def json(self):
        return {'message': self.message}


@pytest.mark.parametrize('crossref_type, entrytype', [
    ('journal-article', 'scholarly article'),
    ('posted-content', 'scholarly article'),
    ('book', 'publication'),
])
def test_preprints_are_scholarly_articles(crossref_type, entrytype):
    publication = Publication.from_crossref(Response({'DOI': '10.1000/x', 'title': ['T'], 'type': crossref_type}))
    assert publication.entrytype == entrytype


# --- export: new authors and journals are known by where they are (#118)

def test_authors_and_journals_of_publications_have_their_kind():
    from MaRDMO.helpers import unique_items
    data = {'publication': {0: {'ID': 'user:p', 'Name': 'Paper', 'Description': 'article',
                                'author': {0: {'ID': 'user:a', 'Name': 'A. Author', 'Description': 'scientist'}},
                                'journal': {0: {'ID': 'user:j', 'Name': 'Journal', 'Description': 'journal'}}}}}
    items, _ = unique_items(data)
    assert {item['Name']: item.get('kind') for item in items.values()} == {
        'Paper': None, 'A. Author': 'author', 'Journal': 'journal'}


def test_placeholders_of_before_0_8_0_are_reported():
    from MaRDMO.checks.base import has_old_id
    assert has_old_id({'ID': 'user:p', 'author': {0: {'ID': 'no author found'}}})
    assert has_old_id({'ID': 'user:p', 'journal': {0: {'ID': 'no journal found'}}})
    assert not has_old_id({'ID': 'user:p', 'author': {0: {'ID': part_id('author', 'A. Author')}}})
