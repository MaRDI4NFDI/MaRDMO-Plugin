'''MathJax was trimmed to what MaRDMO loads (static/MaRDMO/js/mathjax/MARDMO.md, #138).'''
import re
from pathlib import Path

from django.contrib.staticfiles import finders

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'


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
