'''The markers MaRDMO gives the items it exports: class, community, profile type (#141).

An existing item of the MaRDI Portal gets only the markers it lacks and that
do not contradict the ones it has, so it never ends up with a second MaRDMO
class, community or profile type.  A class contradicts if the item has a
class of another MaRDMO family; classes MaRDMO does not use (e.g. *open
source software*) do not count.
'''
from functools import lru_cache

from .getters import get_items
from .model.utils import get_data_properties
from .workflow.constants import IRREPRODUCIBILITY, REPRODUCIBILITY

# Main class of a section (name in items.json): its other classes, and the
# item types of its data-property classes (e.g. "linear model", see
# model.utils.get_data_properties)
FAMILIES = {
    'academic discipline': ((), ()),
    'research problem': ((), ()),
    'mathematical model': ((), ('model',)),
    'computational task': ((), ('task',)),
    'formula': ((), ('equation',)),
    'quantity': (('kind of quantity',), ('quantity', 'quantity kind')),
    'algorithm': ((), ()),
    'algorithmic task': ((), ()),
    'software': ((), ()),
    'benchmark': ((), ()),
    'research workflow': (('transferable research workflow', *REPRODUCIBILITY.values(),
                           *IRREPRODUCIBILITY.values()), ()),
    'process step': ((), ()),
    'computer hardware': ((), ()),
    'CPU model': ((), ()),
    'data set': (('binary data', 'text data', 'proprietary information', 'open data'), ()),
    'method': ((), ()),
    'research tool': ((), ()),
    'programming language': ((), ()),
    'human': ((), ()),
    'scientific journal': ((), ()),
    'publication': (('scholarly article',), ()),
}


@lru_cache(maxsize=None)
def class_families():
    '''``{class QID: names of the families it belongs to}`` for every MaRDMO class.

    Classes of several families (e.g. "ordinary differential equation", a
    data-property class of models, tasks and formulas) belong to all of them.
    '''
    items = get_items()
    families = {}
    for main, (others, data_property_types) in FAMILIES.items():
        members = {items[main], *(items[name] for name in others)}
        for item_type in data_property_types:
            members |= {qid for qid in get_data_properties(item_type).values() if qid}
        for qid in members:
            families.setdefault(qid, set()).add(main)
    return families


def class_contradicts(section_class, item_classes):
    '''Whether *item_classes* (QIDs) contradict the class *section_class* (QID) a section sets.

    True if the item has a MaRDMO class of another family than the section's.
    '''
    families = class_families()
    section = families.get(section_class, set())
    return any(families[qid].isdisjoint(section) for qid in item_classes if qid in families)
