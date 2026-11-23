'''The SPARQL query of the search, in color for the preview, as query services show it.

The query is split into its parts — comments, strings, IRIs, variables,
prefixed names, keywords and functions, numbers — and each part is escaped
and put into a ``<span>`` of its kind (``sparql-comment``, ...); the colors
are in the template (``preview_search.html``).  Everything else is escaped
as it is, so the user's search terms in the query stay text, and the tags
taken away give the query back unchanged.
'''
import html
import re

KEYWORDS = {
    'ASC', 'AS', 'ASK', 'BIND', 'BY', 'CONSTRUCT', 'DESC', 'DESCRIBE', 'DISTINCT', 'EXISTS', 'FILTER',
    'FROM', 'GRAPH', 'GROUP', 'HAVING', 'IN', 'LIMIT', 'MINUS', 'NOT', 'OFFSET', 'OPTIONAL', 'ORDER',
    'PREFIX', 'REDUCED', 'SELECT', 'SERVICE', 'UNION', 'VALUES', 'WHERE',
    # functions
    'BOUND', 'COALESCE', 'CONCAT', 'CONTAINS', 'COUNT', 'DATATYPE', 'IF', 'ISIRI', 'ISLITERAL', 'LANG',
    'LANGMATCHES', 'LCASE', 'REGEX', 'REPLACE', 'SAMPLE', 'STR', 'STRAFTER', 'STRBEFORE', 'STRENDS',
    'STRLEN', 'STRSTARTS', 'SUBSTR', 'UCASE',
}

_TOKENS = re.compile(r'''
    (?P<comment>\#[^\n]*)
  | (?P<string>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
  | (?P<iri><[^<>"{}|^`\\\s]*>)
  | (?P<variable>[?$][A-Za-z_][\w]*)
  | (?P<prefixed>[A-Za-z][\w-]*:[\w-]*)
  | (?P<word>[A-Za-z]+)
  | (?P<number>\d+(?:\.\d+)?)
''', re.VERBOSE)


def _span(kind, text):
    return f'<span class="sparql-{kind}">{html.escape(text)}</span>'


def highlight(query):
    '''Return *query* as HTML: every part escaped, the parts of SPARQL in a ``<span>`` of their kind.'''
    parts, position = [], 0
    for match in _TOKENS.finditer(query):
        parts.append(html.escape(query[position:match.start()]))
        kind, text = match.lastgroup, match.group()
        if kind == 'word':
            parts.append(_span('keyword', text) if text.upper() in KEYWORDS or text == 'a' else html.escape(text))
        else:
            parts.append(_span(kind, text))
        position = match.end()
    parts.append(html.escape(query[position:]))
    return ''.join(parts)
