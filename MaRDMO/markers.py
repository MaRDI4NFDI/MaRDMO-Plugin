'''The markers MaRDMO gives the items it exports: class, community, profile type (#141).

An existing item of the MaRDI Portal gets only the markers it lacks and that
do not contradict the ones it has, so it never ends up with a second MaRDMO
class, community or profile type.  A class contradicts if the item has a
class of another MaRDMO family; classes MaRDMO does not use (e.g. *open
source software*) do not count.
'''
from dataclasses import dataclass
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


# The property of each kind of marker (name in properties.json)
MARKER_PROPERTIES = {'class': 'instance of', 'community': 'community', 'profile': 'MaRDI profile type'}


@dataclass(frozen=True)
class Markers:
    '''The markers a section gives its items: names of items in items.json, or ``None``.'''
    cls: str
    community: str | None = None
    profile: str | None = None

    def qids(self):
        '''``{'class': QID, 'community': QID or None, 'profile': QID or None}``.'''
        items = get_items()
        return {'class': items[self.cls],
                'community': items[self.community] if self.community else None,
                'profile': items[self.profile] if self.profile else None}


# Markers of the authors, journals and publications; every catalog has them
PUBLICATION_MARKERS = {
    'author': Markers('human', None, 'MaRDI person profile'),
    'journal': Markers('scientific journal', None, 'MaRDI journal profile'),
    'publication': Markers('publication', None, 'MaRDI publication profile'),
    'scholarly article': Markers('scholarly article', None, 'MaRDI publication profile'),
}
_SOFTWARE = {
    'software': Markers('software', None, 'MaRDI software profile'),
    # Software that implements an algorithm of the documentation
    'implementing software': Markers('software', 'MathAlgoDB', 'MaRDI software profile'),
    'programminglanguage': Markers('programming language'),
}

# The markers the export gives the items of each section: {catalog: {section: Markers}}.
# The workers read them from here (PublicationExport._add_common_metadata), the
# preview decides with them whether a portal item may be reused (duplicates.py).
SECTION_MARKERS = {
    'model': {
        'field': Markers('academic discipline', 'MathModDB', 'MaRDI research field profile'),
        'problem': Markers('research problem', 'MathModDB', 'MaRDI research problem profile'),
        'model': Markers('mathematical model', 'MathModDB', 'MaRDI model profile'),
        'task': Markers('computational task', 'MathModDB', 'MaRDI task profile'),
        'formulation': Markers('formula', 'MathModDB', 'MaRDI formula profile'),
        'quantity': Markers('quantity', 'MathModDB', 'MaRDI quantity profile'),
        'quantity kind': Markers('kind of quantity', 'MathModDB', 'MaRDI quantity profile'),
        **PUBLICATION_MARKERS,
    },
    'algorithm': {
        'algorithm': Markers('algorithm', 'MathAlgoDB', 'MaRDI algorithm profile'),
        'problem': Markers('algorithmic task', 'MathAlgoDB', 'MaRDI task profile'),
        'benchmark': Markers('benchmark', 'MathAlgoDB'),
        **_SOFTWARE,
        **PUBLICATION_MARKERS,
    },
    'workflow': {
        'workflow': Markers('research workflow', None, 'MaRDI workflow profile'),
        'processstep': Markers('process step'),
        'algorithm': Markers('algorithm', 'MathAlgoDB', 'MaRDI algorithm profile'),
        'algorithmictask': Markers('algorithmic task', 'MathAlgoDB', 'MaRDI task profile'),
        'hardware': Markers('computer hardware'),
        'cpu': Markers('CPU model'),
        'dataset': Markers('data set', None, 'MaRDI data set profile'),
        'method': Markers('method'),
        'instrument': Markers('research tool'),
        'academicdiscipline': Markers('academic discipline'),
        **_SOFTWARE,
        **PUBLICATION_MARKERS,
    },
}


def allowed(kind, value, portal):
    '''Whether the marker *kind* (``class``, ``community``, ``profile``) *value* (QID) may be added.

    *portal* are the markers of an existing portal item (``{'class': set,
    'community': set, 'profile': set}``): it gets only a marker it lacks and
    that does not contradict its own.
    '''
    if kind == 'class':
        return not class_contradicts(value, portal['class'])
    return not portal[kind] or value in portal[kind]


def contradictions(markers, portal):
    '''The kinds (``class``, ``community``, ``profile``) of *markers* (:class:`Markers`)
    that contradict the markers *portal* of an existing item: empty if it may be reused.'''
    return [kind for kind, value in markers.qids().items() if value and not allowed(kind, value, portal)]


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
