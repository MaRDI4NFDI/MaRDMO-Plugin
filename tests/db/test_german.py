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
from tests.db.test_preview_gate import URL, text, without_description

GERMAN = {'HTTP_ACCEPT_LANGUAGE': 'de'}


def preview(client, documentation):
    response = client.get(URL.format(documentation.pk), **GERMAN)
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.django_db
def test_the_preview_is_german(white, client):
    html = preview(client, white)
    page = text(html)
    for german in ('Mathematische Modelle', 'Formeln', 'Kurzbeschreibung', 'Beziehungen: Forschungsprobleme'):
        assert german in page
    assert 'value="Zum MaRDI Portal exportieren"' in html and 'value="Abbrechen"' in html
    for english in ('Short Description', 'Relations to', 'Export to MaRDI Portal', 'NOT DOCUMENTED'):
        assert english not in html


@pytest.mark.django_db
def test_problems_are_german(white, client):
    without_description(white, 'formulation', 1)
    page = text(preview(client, white))
    assert 'Bevor Sie exportieren können' in page
    assert 'Formel , conservation law for the opiate-using career ODE model (F2)' in page
    assert 'Kurzbeschreibung fehlt' in page and 'Missing Short Description' not in page


@pytest.mark.django_db
def test_the_export_page_is_german(white, client):
    assert 'value="Zum MaRDI Portal exportieren"' in preview(client, white)
    without_description(white, 'formulation', 1)       # after the preview
    page = text(client.post(URL.format(white.pk), {}, **GERMAN).content.decode())
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
