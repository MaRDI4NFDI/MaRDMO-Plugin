'''The preview of the synthetic documentations (tools/synthetic) as the user opens it.

Everything of the catalog on one page: the preview renders every page,
looks up the citations of the new publications by their DOI (Crossref,
DataCite, doi.org, zbMATH, ORCID), finds nothing on the MaRDI Portal to
reuse, and runs every check and the export's own checks: nothing prevents
the export.  The answers of the services are recorded::

    RECORD=1 QUESTIONNAIRE=... pytest tests/db/test_synthetic_preview.py --force-enable-socket
'''
import pytest
from rdmo.projects.models import Membership

from tests.db.test_export import imported
from tests.db.test_synthetic_build import BUILDS, PROJECTS
from tests.support.html import element, elements, export_button, preview_page, text
from tools.synthetic.catalog import Catalog

BUILT = [name for name in sorted(BUILDS) if (PROJECTS / f'{name}.xml').exists()]


@pytest.mark.parametrize('name', BUILT)
def test_the_preview_offers_the_export(name, project, portal, client, django_user_model, questionnaire):
    portal(f'export_{name}', f'preview_{name}')
    documentation = imported(project, name)
    owner = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=owner, role='owner')
    client.force_login(owner)
    html = preview_page(client, documentation)
    assert not elements(html, id='before-export'), text(element(html, id='before-export'))
    assert export_button(html) == 'enabled'
    # Every page of the documentation's sections is in the preview (the basics catalog has
    # no quantities, though MaRDMO stores some, see the findings of #138)
    sections = {page.attribute for page in Catalog.read(questionnaire.path, BUILDS[name][0]).pages if page.attribute}
    for value in documentation.values.filter(snapshot=None, set_prefix='', attribute__uri__endswith='/id'):
        path = value.attribute.uri.split('/domain/', 1)[1]
        section = path.split('/')[0]
        if path.count('/') == 1 and section in sections:        # <section>/id: a page (not an author's ID)
            assert elements(html, id=f'page-{section}-{value.set_index}'), f'{section} {value.set_index}'
