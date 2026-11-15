'''The German catalog: every text of the code is translated, and the .mo matches the .po.

After changing a text, run ``python tools/messages.py``, translate what it
reports as new in MaRDMO/locale/de/LC_MESSAGES/django.po, and run it again
(see docs/how-to/mardmo/translate.md).
'''
import re

import polib
import pytest

from tools.messages import CATALOG, problems

PLACEHOLDER = re.compile(r'\{[a-z_]+\}|%\([a-z_]+\)s')


def test_the_german_catalog_is_complete_and_compiled():
    assert problems() == []


@pytest.mark.parametrize('entry', [entry for entry in polib.pofile(str(CATALOG)) if entry.msgid],
                         ids=lambda entry: entry.msgid[:40])
def test_translations_keep_the_placeholders(entry):
    translations = list(entry.msgstr_plural.values()) if entry.msgid_plural else [entry.msgstr]
    for translation in translations:
        assert sorted(set(PLACEHOLDER.findall(translation))) == sorted(set(PLACEHOLDER.findall(entry.msgid)))
