'''The JSON data files in MaRDMO/**/data: they load, and the ID files agree.'''
import json
import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'
DATA_FILES = sorted(PACKAGE.glob('**/data/*.json'))


@pytest.mark.parametrize('path', DATA_FILES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_data_file_is_valid_json(path):
    with open(path, encoding='utf-8') as file:
        assert json.load(file)


def load(name):
    with open(PACKAGE / 'data' / name, encoding='utf-8') as file:
        return json.load(file)


@pytest.mark.parametrize('name, pattern', [
    ('items', r'Q\d+'),
    ('properties', r'P\d+'),
])
@pytest.mark.parametrize('suffix', ['', '_staging'])
def test_ids_are_wikibase_ids_without_duplicates(name, pattern, suffix):
    ids = load(f'{name}{suffix}.json')
    malformed = {key: value for key, value in ids.items() if not re.fullmatch(pattern, value)}
    assert not malformed
    seen = {}
    duplicates = {value: (seen[value], key) for key, value in ids.items() if seen.setdefault(value, key) != key}
    assert not duplicates


@pytest.mark.parametrize('name', ['items', 'properties'])
def test_portal_and_staging_know_the_same_names(name):
    '''Every name the code looks up must exist for both providers.'''
    portal, staging = load(f'{name}.json'), load(f'{name}_staging.json')
    assert sorted(portal.keys() - staging.keys()) == []
    assert sorted(staging.keys() - portal.keys()) == []


@pytest.mark.parametrize('path', sorted(PACKAGE.glob('*/data/mapping.json')),
                         ids=lambda p: p.parent.parent.name)
def test_relation_mapping_keys_are_unique(path):
    '''URLs may repeat: contains_model, contains_task, ... are all "contains".'''
    with open(path, encoding='utf-8') as file:
        mapping = json.load(file)
    keys = [entry['key'] for entry in mapping]
    assert len(keys) == len(set(keys))
