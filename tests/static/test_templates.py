'''Every template compiles (tags, filters and {% load %} libraries exist).'''
from pathlib import Path

import pytest
from django.template.loader import get_template

TEMPLATES = Path(__file__).parents[2] / 'MaRDMO' / 'templates'


@pytest.mark.parametrize('path', sorted(TEMPLATES.glob('**/*.html')),
                         ids=lambda p: str(p.relative_to(TEMPLATES)))
def test_template_compiles(path):
    get_template(str(path.relative_to(TEMPLATES)))
