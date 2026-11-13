'''MkDocs hook: the tables of docs/vocabulary.md, built from MaRDMO's data files (#145).

The page holds the placeholders ``<!-- vocabulary: items -->`` and
``<!-- vocabulary: properties -->``; each becomes a heading with the count
and a table of every entry of ``MaRDMO/data/items.json`` or
``properties.json``, sorted by label (ignoring case), linked to the MaRDI
Portal.  So the page cannot drift from the data files.
'''
import json
from pathlib import Path

PAGE = 'vocabulary.md'
DATA = Path(__file__).parents[1] / 'MaRDMO' / 'data'
PORTAL = 'https://portal.mardi4nfdi.de/wiki'
# Placeholder: (data file, heading, ID column, wiki namespace)
TABLES = {
    '<!-- vocabulary: items -->': ('items.json', 'Items', 'QID', 'Item'),
    '<!-- vocabulary: properties -->': ('properties.json', 'Properties', 'PID', 'Property'),
}


def table(entries, heading, id_column, namespace):
    '''The heading with the count and the table of *entries* (``{label: ID}``).'''
    rows = [f'| {label} | [{identifier}]({PORTAL}/{namespace}:{identifier}) |'
            for label, identifier in sorted(entries.items(), key=lambda entry: entry[0].lower())]
    return '\n'.join([f'## {heading} ({len(entries)})', '', f'| Label | {id_column} |', '|---|---|', *rows])


def render(markdown):
    '''*markdown* with every placeholder replaced by its table.'''
    for placeholder, (file_name, heading, id_column, namespace) in TABLES.items():
        entries = json.loads((DATA / file_name).read_text(encoding='utf-8'))
        markdown = markdown.replace(placeholder, table(entries, heading, id_column, namespace))
    return markdown


def on_page_markdown(markdown, page, **kwargs):
    '''MkDocs event: fill the tables of the vocabulary page.'''
    return render(markdown) if page.file.src_uri == PAGE else markdown
