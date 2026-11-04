'''The SPARQL templates: their placeholders are known and they parse.

The templates are filled with str.format: numbered placeholders take the
values (item IDs, DOIs), named ones the IDs from data/items.json and
data/properties.json (see handler_base.py).  The prefixes (wd:, wdt:, ...)
are predefined by the query services, so they are declared here.
'''
import json
import re
import string
from pathlib import Path

import pytest
from rdflib.plugins.sparql.parser import parseQuery

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'
QUERIES = sorted(PACKAGE.glob('**/*.sparql'))


def load(name):
    with open(PACKAGE / 'data' / name, encoding='utf-8') as file:
        return json.load(file)


def placeholders(text):
    return [name for _, name, _, _ in string.Formatter().parse(text) if name is not None]


def fill(text):
    '''Fill every placeholder with something valid at its place.'''
    parts = []
    for literal, name, _, _ in string.Formatter().parse(text):
        parts.append(literal)
        if name is None:
            continue
        before = ''.join(parts)[-1:]
        if before == ':':      # wd:{0}, wdt:{instance of}
            parts.append('X1')
        elif before == '"':    # "{0}"
            parts.append('x')
        else:                  # VALUES ?id {{{0}}}
            parts.append('wd:Q1')
    query = ''.join(parts)
    prefixes = sorted(set(re.findall(r'(?<![\w<"/])([A-Za-z][\w-]*):(?!//)', query)))
    declarations = ''.join(f'PREFIX {prefix}: <https://example.org/{prefix}/>\n' for prefix in prefixes)
    return declarations + query


@pytest.mark.parametrize('path', QUERIES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_named_placeholders_are_known_ids(path):
    known = load('items.json').keys() | load('properties.json').keys()
    names = {name for name in placeholders(path.read_text(encoding='utf-8')) if name and not name.isdigit()}
    assert sorted(names - known) == []


@pytest.mark.parametrize('path', QUERIES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_query_parses(path):
    parseQuery(fill(path.read_text(encoding='utf-8')))
