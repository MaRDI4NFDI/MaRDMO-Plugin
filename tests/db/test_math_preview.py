'''MaRDMO's interview page: RDMO's own, with MaRDMO's rendering of LaTeX (MaRDMO/js/math-preview.js, #190).

MaRDMO's template extends RDMO's template of the same name; the browser test
(tests/browser/test_math_preview.py) shows the rendering itself.
'''
import re

from rdmo.projects.models import Membership


def test_the_interview_page_is_rdmos_with_maRDMOs_script(project, client, django_user_model):
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    client.force_login(user)
    html = client.get(f'/projects/{documentation.pk}/interview/').content.decode()
    # RDMO's page and script, and MaRDMO's after it, with MaRDMO's MathJax
    assert 'id="main" class="interview"' in html
    assert html.index('projects/js/interview.js') < html.index('MaRDMO/js/math-preview.js')
    # RDMO's static tag adds its version (?v=…)
    assert re.search(r'data-mathjax="[^"]*MaRDMO/js/mathjax/es5/tex-mml-chtml\.js(\?[^"]*)?"', html)
    assert 'data-text-error="MathJax cannot show this formula:"' in html
    # Where it asks for the portal's verdict, with the page's CSRF token
    assert 'data-tex-check="/services/tex-check/"' in html
    assert re.search(r'data-csrf="[A-Za-z0-9]{32,}"', html)
    assert 'data-text-portal="The MaRDI Portal does not accept this formula:"' in html
