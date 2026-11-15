'''MaRDMO's translations: extract the texts, update the German catalog, compile it.

Run from the repository root::

    python tools/messages.py           # update MaRDMO/locale/de/LC_MESSAGES/django.po and .mo
    python tools/messages.py --check   # only report what is missing or out of date (exit code 1)

It does what Django's ``makemessages`` and ``compilemessages`` do, without
GNU gettext: Babel reads the texts of the Python code, Django's
``templatize`` those of the templates, and the labels of the relations and
properties the preview shows come from the data files.  Translations already
in the catalog are kept; texts no longer used are removed.  New texts get an
empty translation, which ``--check`` (and ``tests/static/test_translations.py``)
reports.

Needs ``babel`` and ``polib`` (``pip install -e ".[test]"``).
'''
import argparse
import io
import json
import sys
from pathlib import Path

import polib
from babel.messages.extract import extract

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'MaRDMO'
CATALOG = PACKAGE / 'locale' / 'de' / 'LC_MESSAGES' / 'django.po'

# gettext functions of the Python code and of templatize's output
KEYWORDS = {
    '_': None, 'N_': None, 'gettext': None, 'gettext_lazy': None, 'gettext_noop': None,
    'ngettext': (1, 2), 'ngettext_lazy': (1, 2),
    'pgettext': ((1, 'c'), 2), 'pgettext_lazy': ((1, 'c'), 2),
    'npgettext': ((1, 'c'), 2, 3), 'npgettext_lazy': ((1, 'c'), 2, 3),
}
# Labels the preview shows from the data files ({% translate label %})
DATA_LABELS = ['model/data/mapping.json', 'algorithm/data/mapping.json']

HEADER = {
    'Project-Id-Version': 'MaRDMO',
    'Language': 'de',
    'MIME-Version': '1.0',
    'Content-Type': 'text/plain; charset=UTF-8',
    'Content-Transfer-Encoding': '8bit',
    'Plural-Forms': 'nplurals=2; plural=(n != 1);',
}


def _django():
    '''Configure Django just enough for ``templatize``.'''
    import django
    from django.conf import settings
    if not settings.configured:
        settings.configure(USE_I18N=True)
        django.setup()


def _add(found, msgid, plural, context, where, flags=()):
    key = (context, msgid)
    entry = found.setdefault(key, {'msgid': msgid, 'plural': plural, 'context': context,
                                   'where': [], 'flags': set()})
    entry['where'].append(where)
    entry['flags'].update(flags)


def _extract_source(found, source, method, where_of):
    for lineno, message, comments, context in extract(method, io.BytesIO(source.encode('utf-8')),
                                                       keywords=KEYWORDS, comment_tags=('Translators',)):
        msgid, plural = (message[0], message[1]) if isinstance(message, tuple) else (message, None)
        if msgid:
            flags = ('python-format',) if '%(' in msgid or '%s' in msgid else ()
            _add(found, msgid, plural, context, where_of(lineno), flags)


def extract_messages():
    '''All texts to translate: ``{(context, msgid): entry}``, in order of appearance.'''
    _django()
    from django.utils.translation.template import templatize

    found = {}
    for path in sorted(PACKAGE.rglob('*.py')):
        if 'locale' in path.parts:
            continue
        relative = path.relative_to(ROOT)
        _extract_source(found, path.read_text(encoding='utf-8'), 'python', lambda line, r=relative: (str(r), line))
    for path in sorted((PACKAGE / 'templates').rglob('*.html')):
        relative = path.relative_to(ROOT)
        code = templatize(path.read_text(encoding='utf-8'), origin=str(path))
        # templatize writes for xgettext, which ignores indentation; Babel's
        # tokenizer does not.  Texts are single lines ({% blocktranslate trimmed %}).
        code = '\n'.join(line.lstrip() for line in code.splitlines())
        _extract_source(found, code, 'python', lambda line, r=relative: (str(r), line))
    for name in DATA_LABELS:
        for row in json.loads((PACKAGE / name).read_text(encoding='utf-8')):
            if row.get('label'):
                _add(found, row['label'], None, None, (f'MaRDMO/{name}', 0))
    return found


def updated_catalog():
    '''The catalog with the texts of the code: translations kept, unused texts left out.'''
    old = polib.pofile(str(CATALOG)) if CATALOG.exists() else polib.POFile()
    translations = {(entry.msgctxt, entry.msgid): entry for entry in old if not entry.obsolete}
    catalog = polib.POFile(wrapwidth=0)
    catalog.metadata = HEADER
    for key, found in extract_messages().items():
        previous = translations.get(key)
        entry = polib.POEntry(
            msgid=found['msgid'],
            msgctxt=found['context'],
            msgstr=previous.msgstr if previous and not found['plural'] else '',
            occurrences=[(where, str(line) if line else '') for where, line in found['where']],
            flags=sorted(found['flags']),
        )
        if found['plural']:
            entry.msgid_plural = found['plural']
            entry.msgstr_plural = (dict(previous.msgstr_plural) if previous and previous.msgstr_plural
                                   else {0: '', 1: ''})
        catalog.append(entry)
    return catalog


def _entries(catalog):
    return {(entry.msgctxt, entry.msgid): (entry.msgstr, dict(entry.msgstr_plural))
            for entry in catalog if not entry.obsolete and entry.msgid}


def problems():
    '''What is wrong with the catalog in the repository, as a list of strings.'''
    wrong = []
    if not CATALOG.exists():
        return [f'{CATALOG.relative_to(ROOT)} is missing']
    stored = polib.pofile(str(CATALOG))
    expected = updated_catalog()
    missing = _entries(expected).keys() - _entries(stored).keys()
    unused = _entries(stored).keys() - _entries(expected).keys()
    wrong += [f'not in the catalog: {msgid!r}' for __, msgid in sorted(missing, key=str)]
    wrong += [f'no longer used: {msgid!r}' for __, msgid in sorted(unused, key=str)]
    for entry in stored:
        if entry.obsolete or not entry.msgid:
            continue
        if 'fuzzy' in entry.flags:
            wrong.append(f'fuzzy: {entry.msgid!r}')
        if not (entry.msgstr or all(entry.msgstr_plural.values()) and entry.msgstr_plural):
            wrong.append(f'not translated: {entry.msgid!r}')
    compiled = CATALOG.with_suffix('.mo')
    translated = {key: value for key, value in _entries(stored).items() if value[0] or any(value[1].values())}
    if not compiled.exists() or _entries(polib.mofile(str(compiled))) != translated:
        wrong.append(f'{compiled.relative_to(ROOT)} does not match the .po file (run tools/messages.py)')
    return wrong


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true', help='only report, change nothing')
    if parser.parse_args().check:
        wrong = problems()
        print('\n'.join(wrong) or 'The German catalog is complete and compiled.')
        return 1 if wrong else 0
    catalog = updated_catalog()
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    catalog.save(str(CATALOG))
    catalog.save_as_mofile(str(CATALOG.with_suffix('.mo')))
    untranslated = [entry.msgid for entry in catalog if not entry.translated()]
    print(f'{len(catalog)} texts, {len(untranslated)} without translation: {CATALOG.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
