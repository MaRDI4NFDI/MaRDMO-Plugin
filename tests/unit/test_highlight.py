'''The SPARQL query of the search in color (MaRDMO.search.highlight).

Every part gets the span of its kind; the tags taken away give the query
back unchanged, and the user's text in it stays text.
'''
import html
import re

import pytest

from MaRDMO.search.highlight import highlight

QUERY = '''SELECT DISTINCT ?label ?description ?qid
WHERE {
  ?model wdt:P31 wd:Q68663 ;
         rdfs:label ?label .
  FILTER(LANG(?label) = "en")
  # research problem: spreading of infectious diseases
  FILTER(CONTAINS(LCASE(?label), "sir \\"model\\" # not a comment"))
  ?model <https://example.org/prop> 'x' .
  BIND(STRAFTER(STR(?model), STR(wd:)) AS ?qid)
}
ORDER BY LCASE(?label)
LIMIT 101'''


def spans(text, kind):
    return [html.unescape(found) for found in re.findall(rf'<span class="sparql-{kind}">(.*?)</span>', text)]


def plain(text):
    return html.unescape(re.sub(r'</?span[^>]*>', '', text))


def test_every_part_has_its_kind():
    colored = highlight(QUERY)
    assert spans(colored, 'keyword') == ['SELECT', 'DISTINCT', 'WHERE', 'FILTER', 'LANG', 'FILTER', 'CONTAINS',
                                         'LCASE', 'BIND', 'STRAFTER', 'STR', 'STR', 'AS', 'ORDER', 'BY',
                                         'LCASE', 'LIMIT']
    assert spans(colored, 'variable')[:3] == ['?label', '?description', '?qid']
    assert spans(colored, 'prefixed') == ['wdt:P31', 'wd:Q68663', 'rdfs:label', 'wd:']
    assert spans(colored, 'string') == ['"en"', '"sir \\"model\\" # not a comment"', "'x'"]
    assert spans(colored, 'comment') == ['# research problem: spreading of infectious diseases']
    assert spans(colored, 'iri') == ['<https://example.org/prop>']
    assert spans(colored, 'number') == ['101']


def test_a_keyword_in_a_comment_or_a_name_is_not_one():
    colored = highlight('# SELECT the best\n?x rdfs:label ?y')
    assert spans(colored, 'keyword') == [] and spans(colored, 'prefixed') == ['rdfs:label']


@pytest.mark.parametrize('query', [QUERY, '', 'no sparql here', 'FILTER(?x < 3 && ?y > "a<b")'])
def test_the_query_comes_back_unchanged(query):
    assert plain(highlight(query)) == query


@pytest.mark.parametrize('text', ['"<script>alert(1)</script>"', '# <img src=x onerror=alert(1)>',
                                  '?x <b> & </b>'])
def test_the_users_text_stays_text(text):
    colored = highlight(text)
    assert not re.search(r'<(?!/?span[ >])', colored)       # no tag but the spans
    assert plain(colored) == text
