'''The option set providers search as recorded in tests/data/providers.json.

The file was recorded from the 61 classes of MaRDMO 0.6 (one per provider
key) before they became MaRDMOProvider with the table in MaRDMO.optionsets:
item class, sources, "not found", the user's own items, creation and
refresh.  Since then providers of programming languages and software search
from the first character (C, R), all others from three (six workflow
providers searched from one before); the provider "Instrument", used by no
option set, was removed.
'''
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from MaRDMO.optionsets import OPTIONSET_PROVIDERS, PROVIDERS
from tests.provider_calls import record

GOLDEN = json.loads((Path(__file__).parents[1] / 'data' / 'providers.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('key', sorted(GOLDEN))
def test_provider_searches_as_recorded(key, monkeypatch):
    expected = {name: GOLDEN[key][name] for name in ('search', 'refresh', 'calls')}
    assert record('MaRDMO.providers.MaRDMOProvider', key, monkeypatch) == expected


def test_programming_languages_and_software_search_from_the_first_character():
    '''A single letter finds C or R; elsewhere it matches hundreds of items and slows the search.'''
    from_one = {key for key, entry in GOLDEN.items() if entry['calls']['a']}
    assert from_one == {key for key, search in PROVIDERS.items()
                        if any(name in ('software', 'programming language')
                               for name in ([search.item_class] if isinstance(search.item_class, str)
                                            else search.item_class))}
    assert all(GOLDEN[key]['calls']['ab'] is None for key in GOLDEN.keys() - from_one)
    assert not any(entry['calls'][''] for entry in GOLDEN.values())


def test_setting_lists_every_provider_with_its_label():
    listed = {key: (str(label), path) for key, label, path in OPTIONSET_PROVIDERS}
    assert listed.keys() == GOLDEN.keys() == PROVIDERS.keys()
    assert all(path == 'MaRDMO.providers.MaRDMOProvider' for _, path in listed.values())
    assert {key: label for key, (label, _) in listed.items()} == {key: entry['label'] for key, entry in GOLDEN.items()}


def test_settings_can_import_the_list_before_django_starts():
    '''The RDMO settings import it; RDMO's models must not load then.'''
    env = {k: v for k, v in os.environ.items() if k != 'DJANGO_SETTINGS_MODULE'}
    code = 'from MaRDMO.optionsets import OPTIONSET_PROVIDERS; print(len(OPTIONSET_PROVIDERS))'
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env,
                            cwd=Path(__file__).parents[2])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(len(GOLDEN))
