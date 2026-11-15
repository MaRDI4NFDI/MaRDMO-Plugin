'''MaRDMO in German: the preview, the problems and the export's messages (#138).

The interview's language decides: the preview of white_2006 is German, the
checks report German messages with German section names, the error page of
the export is German.  What goes to the MaRDI Portal stays English (the
payload is compared in English by tests/db/test_export.py, and it does not
depend on the language).
'''
import threading

import pytest
from django.utils import translation

from MaRDMO.oauth2 import in_language
from tests.db.conftest import without_description
from tests.support.html import element, export_button, export_page, preview_page, text


def preview(client, documentation):
    return preview_page(client, documentation, language='de')


@pytest.mark.django_db
def test_the_preview_is_german(white, client):
    html = preview(client, white)
    page = text(html)
    for german in ('Mathematische Modelle', 'Formeln', 'Kurzbeschreibung', 'Beziehungen: Forschungsprobleme'):
        assert german in page
    assert export_button(html) == 'enabled'
    assert 'value="Zum MaRDI Portal exportieren"' in html and 'value="Abbrechen"' in html
    for english in ('Short Description', 'Relations to', 'Export to MaRDI Portal', 'NOT DOCUMENTED'):
        assert english not in html


@pytest.mark.django_db
def test_problems_are_german(white, client):
    without_description(white, 'formulation', 1)
    html = preview(client, white)
    box = text(element(html, id='before-export'))
    assert 'Bevor Sie exportieren können' in box and 'Fehler, Widersprüche und unvollständige Dokumentation' in box
    assert 'Formel, conservation law for the opiate-using career ODE model (F2) Zum Interview' in box
    assert 'Kurzbeschreibung fehlt' in box and 'Missing Short Description' not in html
    assert 'Beheben Sie die Punkte oben' in text(element(html, id='export-blocked'))


@pytest.mark.django_db
def test_the_export_page_is_german(white, client):
    assert export_button(preview(client, white)) == 'enabled'
    without_description(white, 'formulation', 1)       # after the preview
    page = text(export_page(client, white, language='de').content.decode())
    assert 'Seit der Vorschau hat sich etwas geändert' in page
    assert 'Formel (Seite F2): Kurzbeschreibung fehlt' in page


def test_the_upload_thread_keeps_the_language():
    seen = []
    with translation.override('de'):
        thread = threading.Thread(target=in_language(translation.get_language(), lambda: seen.append(
            (translation.get_language(), str(translation.gettext('Upload failed'))))))
    thread.start()
    thread.join()
    assert seen == [('de', 'Upload fehlgeschlagen')]
