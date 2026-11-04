'''Meaning qualifiers are only written on the properties the qualifier merge rechecks.

The SPARQL existence check also finds a portal statement with a role or
platform for one without; merge_qualifiers checks found statements of
_MEANING_PROPERTIES again.  A relation with a role on another property
would slip through, so it has to be added there.
'''
import re
from pathlib import Path

import pytest

from MaRDMO.algorithm.constants import get_relations as algorithm_relations
from MaRDMO.getters import get_properties
from MaRDMO.model.constants import get_relations as model_relations
from MaRDMO.payload import _MEANING_PROPERTIES
from MaRDMO.workflow.constants import get_relations as workflow_relations

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'


@pytest.fixture
def rechecked():
    properties = get_properties()
    return {properties[name] for name in _MEANING_PROPERTIES}


@pytest.mark.parametrize('relations', [model_relations, algorithm_relations, workflow_relations],
                         ids=['model', 'algorithm', 'workflow'])
def test_relations_with_a_role_are_rechecked(relations, rechecked):
    # [property, role item] gets the role as "object has role" (payload.add_multiple_relation)
    with_role = {url: entry[0] for url, entry in relations().items()
                 if len(entry) == 2 and entry[1] not in ('forward', 'backward')}
    assert with_role
    assert {url: prop for url, prop in with_role.items() if prop not in rechecked} == {}


def test_platforms_are_qualifiers_of_uses():
    source = (PACKAGE / 'workflow' / 'worker.py').read_text(encoding='utf-8')
    platforms = [m.end() for m in re.finditer(r'self\.properties\["platform"\]', source)]
    assert platforms
    for position in platforms:
        verb = re.search(r'verb\s*=\s*self\.properties\["([^"]+)"\]', source[position:])
        assert verb and verb.group(1) in _MEANING_PROPERTIES
