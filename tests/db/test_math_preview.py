'''MaRDMO's interview page: RDMO's own, with MaRDMO's rendering of LaTeX (MaRDMO/js/math-preview.js).

MaRDMO's template extends RDMO's template of the same name; the browser test
(tests/browser/test_math_preview.py) shows the rendering itself.
'''
import re
from pathlib import Path

from django.contrib.staticfiles import finders
from rdmo.projects.models import Membership

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'


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


def test_every_mathjax_file_a_template_loads_is_there():
    '''MathJax was trimmed to what MaRDMO loads (static/MaRDMO/js/mathjax/MARDMO.md).'''
    loaded = set()
    for template in PACKAGE.joinpath('templates').rglob('*.html'):
        loaded |= set(re.findall(r"MaRDMO/js/mathjax/[\w/.-]+\.js", template.read_text(encoding='utf-8')))
    assert loaded == {'MaRDMO/js/mathjax/es5/tex-mml-chtml.js', 'MaRDMO/js/mathjax/es5/tex-svg.js'}
    assert all(finders.find(path) for path in loaded)
    # What they load on demand: the TeX extensions, the fonts of the HTML output, the explorer
    mathjax = PACKAGE / 'static/MaRDMO/js/mathjax/es5'
    assert (mathjax / 'input/tex/extensions/mhchem.js').exists()
    assert (mathjax / 'output/chtml/fonts/woff-v2/MathJax_Main-Regular.woff').exists()
    assert (mathjax / 'a11y/explorer.js').exists() and (mathjax / 'sre/sre_browser.js').exists()
