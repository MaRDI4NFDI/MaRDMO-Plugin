'''Shared fixtures.

The questionnaire tests read the catalog XML files of MaRDMO-Questionnaire
from the folder in the environment variable QUESTIONNAIRE (CI checks out
the branch of the same name, else main).  Without it they are skipped
locally, but fail in CI, so that they cannot be skipped there unnoticed.
'''
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import pytest

DC_URI = '{http://purl.org/dc/elements/1.1/}uri'


@dataclass
class Questionnaire:
    '''The URIs of the elements in the catalog XML files, by element type.'''
    path: Path
    uris: dict = field(default_factory=dict)

    def __getitem__(self, tag):
        return self.uris.get(tag, set())


@pytest.fixture(scope='session')
def questionnaire():
    folder = os.environ.get('QUESTIONNAIRE')
    if not folder:
        if os.environ.get('CI'):
            pytest.fail('QUESTIONNAIRE is not set: the questionnaire checks would not run')
        pytest.skip('QUESTIONNAIRE is not set (path to MaRDMO-Questionnaire/catalog)')
    path = Path(folder)
    files = sorted(path.glob('*.xml'))
    assert files, f'no catalog XML files in {path}'
    result = Questionnaire(path)
    for file in files:
        for element in ET.parse(file).getroot():
            result.uris.setdefault(element.tag, set()).add(element.get(DC_URI))
    return result


@pytest.fixture(autouse=True)
def empty_cache():
    '''Every test starts with an empty cache, so a test does not depend on the tests before.

    MaRDMO caches answers of the portal (e.g. the TeX checker's verdicts); a
    test that found them cached would not send, and not record, its requests.
    '''
    from django.core.cache import cache
    cache.clear()
