'''Every item the model and algorithm exports create gets its community.

Quantities lost "community: MathModDB" in 0.3.4, when the community became an
optional argument of _add_common_metadata and the quantity calls were not
given it.  The workers read their markers from markers.SECTION_MARKERS
(#141); software gets MathAlgoDB only if it implements the documented
algorithm ("implementing software").
'''
import pytest

from MaRDMO.markers import PUBLICATION_MARKERS, SECTION_MARKERS


def test_every_model_item_belongs_to_mathmoddb():
    assert [section for section, markers in SECTION_MARKERS['model'].items()
            if section not in PUBLICATION_MARKERS and markers.community != 'MathModDB'] == []


@pytest.mark.parametrize('catalog, classes', [
    ('algorithm', ['algorithm', 'algorithmic task', 'benchmark', 'software']),
    ('workflow', ['algorithm', 'algorithmic task', 'software']),
])
def test_algorithm_items_belong_to_mathalgodb(catalog, classes):
    for cls in classes:
        communities = {markers.community for section, markers in SECTION_MARKERS[catalog].items()
                       if markers.cls == cls and section != 'software'}
        assert communities == {'MathAlgoDB'}, cls
