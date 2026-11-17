# How to Translate MaRDMO

MaRDMO is in English and German.  The language is the one the user chose in
RDMO; the questionnaire has its own texts in both languages, MaRDMO's
translations are in `MaRDMO/locale/de/LC_MESSAGES/django.po` (compiled to
`django.mo`, which is part of the package).

## What is translated, and what is not

| Translated | Stays English |
|---|---|
| The preview: headings, labels, the notes, *Before you export* | What goes to the MaRDI Portal: labels, descriptions, the generic descriptions of own items without page |
| The problems of the checks (list and red marks), the error pages of the export | Option texts stored in answers (*new item*) and the source tags (`[mardi]`, `[wikidata]`) |
| The validators' messages in the interview | The logs |
| The progress page and the result page of the export | Messages of the MaRDI Portal, passed on unchanged |

A German user must not export German descriptions: whatever is stored or
sent is English.

The terms follow the German questionnaire (*Quantität*, *Quantitätsart*,
*Berechnungsaufgabe*, *Forschungsproblem*, *Datensatz*, *Prozessschritt*,
…); the relation and property labels are the German texts of the
questionnaire's options.  The users are addressed with *Sie*.

## Marking a text

**Python.**  Use `gettext` for texts made while a request runs and
`gettext_lazy` for texts at module level.  Values go in with placeholders,
not with f-strings, so the translation can put them elsewhere:

```python
from django.utils.translation import gettext as _, gettext_noop as N_

self.err.append(self._error(N_('Process Step'), page_name,
                            _('Missing {item}').format(item=_(to_class)), field='RelationA'))
```

Sections and class names (`'Process Step'`, `SECTION_MAP`) stay English in
the problems, they group them; they are marked with `N_` so that the catalog
has them, and translated where they are shown (`str(Problem)`, the list
*Before you export*).  A message that inserts a class name avoids German
articles and adjective endings (*{item} fehlt*, not *Fehlender {item}*).

**The upload** runs in a thread of its own, which has the default language;
`oauth2.in_language` runs it in the language of the request.

**Templates.**  `{% load i18n %}`, then `{% translate "Short Description" %}`;
with values `{% blocktranslate trimmed with kind=values.QorQK %}Definition of
{{ kind }}{% endblocktranslate %}`.  Use `trimmed` always: the tool reads one
text per line.  Arguments of an include are translated with `_("…")`:
`{% include "…" with title=_("Research Problems") %}`.  Labels from the data
files (relations, properties) are translated with `{% translate label %}`;
the tool takes them from `model/data/mapping.json` and
`algorithm/data/mapping.json`.

**JavaScript** gets its texts from the template: the progress page as
`data-text-*` attributes, the graph of the result page as `graph_texts`
(`views.show_success`).

## Updating the catalog

```bash
python tools/messages.py
```

reads the texts of the code and the templates, keeps the existing
translations, removes texts no longer used, and compiles the `.mo`.  New
texts get an empty translation: fill them in `django.po` and run the tool
again.  `python tools/messages.py --check` only reports; the test
`tests/static/test_translations.py` fails while a text has no translation,
a translation has lost a placeholder, or the `.mo` is out of date.

The tool needs no GNU gettext (it uses Babel and polib, installed with
`pip install -e ".[test]"`).  Django's `makemessages` and `compilemessages`
work too where gettext is installed.

## Tests

The tests run in English.  `tests/db/test_german.py` renders the preview,
the problems and the error page of the export in German, and
`tests/db/test_marks.py` checks the red marks of white_2006 once more in
German, including that every section of a problem has its German name.
