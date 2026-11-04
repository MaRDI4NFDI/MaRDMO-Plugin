'''The installation instructions in the README agree with the package and the questionnaire.

docs/index.md includes these sections of the README (pymdownx.snippets), so
the documentation is checked with them.  The versions come from the package
metadata (pyproject.toml), which works without tomllib on Python 3.10.
'''
import importlib
import re
import xml.etree.ElementTree as ET
from importlib.metadata import metadata, requires
from pathlib import Path

import pytest

README = (Path(__file__).parents[2] / 'README.md').read_text(encoding='utf-8')


def section(name):
    '''A README section between the snippet markers <!-- --8<-- [start:name] --> and [end:name].'''
    match = re.search(rf'<!-- --8<-- \[start:{name}\] -->(.*?)<!-- --8<-- \[end:{name}\] -->', README, re.S)
    assert match, f'README section {name!r} is missing'
    return match.group(1)


def minimum(specifier):
    match = re.fullmatch(r'>=\s*([\d.]+)', specifier.strip())
    assert match, f'expected a minimum version (>=x.y), got {specifier!r}'
    return match.group(1)


def test_python_version():
    version = minimum(metadata('MaRDMO')['Requires-Python'])
    assert f'Python {version} or later' in section('requirements')


def test_rdmo_version():
    [rdmo] = [r for r in requires('MaRDMO') if re.match(r'rdmo\b', r, re.I) and 'extra' not in r]
    version = minimum(re.sub(r'^rdmo', '', rdmo, flags=re.I))
    assert f'RDMO {version} or later' in section('requirements')


def classes(text):
    '''(key, dotted path) of the entries of PROJECT_EXPORTS and OPTIONSET_PROVIDERS.'''
    return re.findall(r"\('([\w-]+)',\s*_\('[^']*'\),\s*'(MaRDMO\.[\w.]+)'\)", text)


@pytest.mark.parametrize('key, path', classes(section('install')), ids=lambda value: value)
def test_class_exists(key, path):
    module, name = path.rsplit('.', 1)
    assert hasattr(importlib.import_module(module), name), f'{path} ({key}) does not exist'


def test_both_export_providers_are_listed():
    assert {key for key, _ in classes(section('install'))} >= {'wikibase', 'wikibase-search'}


def test_providers_of_the_questionnaire_are_listed(questionnaire):
    used = set()
    for path in questionnaire.path.glob('*.xml'):
        used |= {element.text for element in ET.parse(path).iter('provider_key') if element.text}
    listed = {key for key, _ in classes(section('install'))}
    assert sorted(used - listed) == []


def test_questionnaire_files_are_imported(questionnaire):
    imported = re.findall(r'catalog/([\w-]+\.xml)', section('questionnaire'))
    assert len(imported) == len(set(imported))
    assert sorted(imported) == sorted(path.name for path in questionnaire.path.glob('*.xml'))
