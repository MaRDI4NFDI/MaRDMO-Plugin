'''RDMO's interview page with MaRDMO: RDMO's own template, MaRDMO's scripts added by its middleware.

MaRDMO replaces no template of RDMO, so another plugin may replace the
interview's template and MaRDMO's rendering of LaTeX still comes.
'''
import pytest
from django.template.loader import get_template
from django.test import override_settings
from django.urls import reverse
from rdmo.projects.models import Membership

PLUGIN_PAGE = '<html><body><p>The interview of another plugin</p></body></html>'


@pytest.fixture
def interview(project, client, django_user_model):
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    client.force_login(user)
    return reverse('project_interview', args=[documentation.pk])


def test_the_interview_is_rdmos_with_mardmos_scripts(interview, client):
    assert '/rdmo/' in get_template('projects/project_interview.html').origin.name
    page = client.get(interview).content.decode()
    assert page.count('MaRDMO/js/math-preview.js') == 1


def test_another_plugins_interview_template_keeps_mardmos_scripts(interview, client, settings, tmp_path):
    folder = tmp_path / 'projects'
    folder.mkdir()
    (folder / 'project_interview.html').write_text(PLUGIN_PAGE)
    templates = [{**settings.TEMPLATES[0], 'DIRS': [tmp_path, *settings.TEMPLATES[0].get('DIRS', [])]}]
    with override_settings(TEMPLATES=templates):
        page = client.get(interview).content.decode()
    assert 'The interview of another plugin' in page and 'MaRDMO/js/math-preview.js' in page
