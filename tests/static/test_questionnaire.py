'''The plugin and the questionnaire agree on attributes and options.

MaRDMO reads and writes answers by attribute URI and option URI; an URI
that was renamed or removed in the questionnaire only shows up at runtime,
as answers that are silently missing.
'''
import json
import re
from pathlib import Path

import pytest

from MaRDMO.constants import BASE_URI

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'

# Relations MaRDMO exports on its own (e.g. model "models" research problem);
# the user never chooses them, so the questionnaire has no option for them
INTERNAL_RELATIONS = {
    'model': {'models', 'used_by'},
    'algorithm': {'implemented_by', 'manifests', 'solves', 'tested_by'},
}


def load(path):
    with open(path, encoding='utf-8') as file:
        return json.load(file)


def uris(config):
    '''All "uri" values in a questions.json, at any depth.'''
    if isinstance(config, dict):
        for key, value in config.items():
            if key == 'uri' and isinstance(value, str):
                yield value
            else:
                yield from uris(value)


@pytest.mark.parametrize('path', sorted(PACKAGE.glob('*/data/questions.json')),
                         ids=lambda p: p.parent.parent.name)
def test_questions_exist_as_attributes(path, questionnaire):
    missing = sorted(uri for uri in uris(load(path)) if f'{BASE_URI}{uri}' not in questionnaire['attribute'])
    assert missing == []


def test_options_exist(questionnaire):
    options = load(PACKAGE / 'data' / 'options.json')
    missing = sorted(key for key, url in options.items() if url not in questionnaire['option'])
    assert missing == []


@pytest.mark.parametrize('path', sorted(PACKAGE.glob('*/data/mapping.json')),
                         ids=lambda p: p.parent.parent.name)
def test_relations_exist_as_options(path, questionnaire):
    internal = INTERNAL_RELATIONS.get(path.parent.parent.name, set())
    mapping = load(path)
    missing = sorted(entry['key'] for entry in mapping
                     if entry['url'] not in questionnaire['option'] and entry['key'] not in internal)
    assert missing == []
    # An internal relation that the questionnaire now offers belongs out of the list
    offered = sorted(entry['key'] for entry in mapping
                     if entry['key'] in internal and entry['url'] in questionnaire['option'])
    assert offered == []


def test_uris_in_code_and_templates_exist(questionnaire):
    '''URIs written out in Python files and templates (attributes, options, option sets).'''
    known = questionnaire['attribute'] | questionnaire['option'] | questionnaire['optionset']
    found = {}
    for path in [*PACKAGE.glob('**/*.py'), *PACKAGE.glob('**/*.html')]:
        for uri in re.findall(rf'{re.escape(BASE_URI)}[\w/-]+', path.read_text(encoding='utf-8')):
            found.setdefault(uri, str(path.relative_to(PACKAGE)))
    missing = {uri: path for uri, path in found.items() if uri not in known}
    assert missing == {}
