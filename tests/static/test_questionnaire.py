'''The plugin and the questionnaire agree on attributes and options.

MaRDMO reads and writes answers by attribute URI and option URI; an URI
that was renamed or removed in the questionnaire only shows up at runtime,
as answers that are silently missing.
'''
import importlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from MaRDMO.constants import BASE_URI
from MaRDMO.optionsets import PROVIDERS
from tests.conftest import DC_URI

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


def provider_keys(questionnaire):
    """The provider keys of the option sets of the questionnaire."""
    keys = set()
    for path in questionnaire.path.glob('*.xml'):
        keys |= {element.text for element in ET.parse(path).iter('provider_key') if element.text}
    return keys


def test_every_option_set_has_a_provider(questionnaire):
    """An option set without a row of MaRDMO.optionsets offers nothing in the interview."""
    assert sorted(provider_keys(questionnaire) - PROVIDERS.keys()) == []


def test_every_provider_is_used_by_an_option_set(questionnaire):
    """A row no option set names is dead code (as the provider "Instrument" was)."""
    assert sorted(PROVIDERS.keys() - provider_keys(questionnaire)) == []


# Imported references are stored at the position of their option in the
# option set, where RDMO's checkbox widget expects them (CheckboxInput.js)
REFERENCE_ORDERS = {
    'software-reference': ['MaRDMO.constants', 'MaRDMO.algorithm.constants', 'MaRDMO.workflow.constants'],
    'benchmark-reference': ['MaRDMO.algorithm.constants'],
    'quantity-reference': ['MaRDMO.model.constants'],
}
REFERENCE_LISTS = {
    'software-reference': 'software_reference_ids',
    'benchmark-reference': 'benchmark_reference_ids',
    'quantity-reference': 'qudt_reference_ids',
}


@pytest.mark.parametrize('optionset, module', [(optionset, module) for optionset, modules in REFERENCE_ORDERS.items()
                                               for module in modules])
def test_reference_lists_have_the_order_of_their_options(optionset, module, questionnaire):
    root = ET.parse(questionnaire.path / 'optionsets.xml').getroot()
    element = next(e for e in root if e.tag == 'optionset' and e.get(DC_URI).endswith(f'/{optionset}'))
    in_questionnaire = [option.get(DC_URI) for option in
                        sorted(element.find('options'), key=lambda option: int(option.get('order') or 0))]
    options = load(PACKAGE / 'data' / 'options.json')
    in_code = [options[key] for key in getattr(importlib.import_module(module), REFERENCE_LISTS[optionset])]
    assert in_code == in_questionnaire
