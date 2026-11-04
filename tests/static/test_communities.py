'''Every item the model and algorithm exports create gets its community.

Quantities lost "community: MathModDB" in 0.3.4, when the community became an
optional argument of _add_common_metadata and the quantity calls were not
given it.  Software gets MathAlgoDB only if it implements the documented
algorithm, so the algorithm export is checked per class.
'''
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'


def calls(path):
    '''(line, class, community) of every _add_common_metadata call in *path*.'''
    found = []
    for node in ast.walk(ast.parse((PACKAGE / path).read_text(encoding='utf-8'))):
        if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == '_add_common_metadata':
            keywords = {k.arg: k.value for k in node.keywords}

            def item(key):
                value = keywords.get(key)
                if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant):
                    return value.slice.value
                return None

            found.append((node.lineno, item('qclass'), item('community')))
    return found


def test_every_model_item_belongs_to_mathmoddb():
    found = calls('model/worker.py')
    assert found
    assert [(line, qclass) for line, qclass, community in found if community != 'MathModDB'] == []


@pytest.mark.parametrize('qclass', ['algorithm', 'algorithmic task', 'benchmark'])
def test_algorithm_items_belong_to_mathalgodb(qclass):
    found = [community for _, cls, community in calls('algorithm/worker.py') if cls == qclass]
    assert found and set(found) == {'MathAlgoDB'}
