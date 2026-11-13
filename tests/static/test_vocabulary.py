'''The vocabulary page lists exactly the items and properties of the data files (#145).'''
import json
import re
from pathlib import Path

import pytest

from docs_hooks.vocabulary import DATA, TABLES, render

ROOT = Path(__file__).parents[2]
PAGE = ROOT / 'docs' / 'vocabulary.md'


def test_the_page_has_the_placeholders_and_mkdocs_runs_the_hook():
    page = PAGE.read_text(encoding='utf-8')
    assert all(page.count(placeholder) == 1 for placeholder in TABLES)
    assert re.search(r'^hooks:\n(  - .*\n)*  - docs_hooks/vocabulary\.py$',
                     (ROOT / 'mkdocs.yml').read_text(encoding='utf-8'), re.M)


@pytest.mark.parametrize('file_name, heading, prefix', [('items.json', 'Items', 'Q'), ('properties.json', 'Properties', 'P')])
def test_every_entry_is_listed_once(file_name, heading, prefix):
    entries = json.loads((DATA / file_name).read_text(encoding='utf-8'))
    rendered = render(PAGE.read_text(encoding='utf-8'))
    assert f'## {heading} ({len(entries)})' in rendered
    rows = re.findall(rf'^\| (.+) \| \[({prefix}\d+)\]\(\S+\) \|$', rendered, re.M)
    assert sorted(rows) == sorted(entries.items())
