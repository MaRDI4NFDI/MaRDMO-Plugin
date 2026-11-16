'''The structure of a MaRDMO catalog, read from the questionnaire's XML files.

Pages, question sets and questions with what the interview needs to store
an answer: the attribute, whether a page or question set is a collection
(it adds a set level), whether a question takes several answers, its
widget and its options (fixed options or a provider), and its conditions.
Needs no Django: the generator and the completeness tests use it.

    >>> catalog = Catalog.read(folder, 'mardmo-model-catalog')
    >>> question = catalog.question('formulation/element/symbol')
    >>> [element.key for element in question.path]
    ['formulation', 'formulation/...', ...]
'''
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DC = '{http://purl.org/dc/elements/1.1/}uri'
TERMS = 'https://rdmo.mardi4nfdi.de/terms/'
DOMAIN = TERMS + 'domain/'
OPTIONS = TERMS + 'options/'


def _short(uri, prefix):
    return uri[len(prefix):] if uri and uri.startswith(prefix) else uri


@dataclass
class Condition:
    '''Shown if the answer of *source* (attribute key) relates (*relation*) to *option* (option key) or *text*.'''
    key: str
    source: str
    relation: str
    option: Optional[str]
    text: str


@dataclass
class OptionSet:
    key: str
    provider: str = ''
    options: list = field(default_factory=list)      # option keys, in their order


@dataclass
class Element:
    '''A page, question set or question.'''
    kind: str                       # 'page', 'questionset', 'question'
    uri: str
    attribute: Optional[str]        # attribute key below domain/ ("formulation/name"), or None
    is_collection: bool
    parent: Optional['Element'] = None
    children: list = field(default_factory=list)
    conditions: list = field(default_factory=list)
    # Questions only
    widget: str = ''
    value_type: str = ''
    optionsets: list = field(default_factory=list)
    is_optional: bool = False
    title: str = ''

    @property
    def key(self):
        return self.attribute or _short(self.uri, TERMS + 'questions/')

    @property
    def path(self):
        '''The page, question sets and the element itself, from the page down.'''
        chain, element = [], self
        while element is not None:
            chain.append(element)
            element = element.parent
        return chain[::-1]

    @property
    def sets(self):
        '''The page and question sets around a question: each adds a level to ``set_prefix``.'''
        return self.path[:-1] if self.kind == 'question' else self.path

    @property
    def providers(self):
        return [optionset.provider for optionset in self.optionsets if optionset.provider]

    @property
    def options(self):
        return [option for optionset in self.optionsets for option in optionset.options]

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Catalog:
    name: str
    pages: list
    conditions: dict
    # Option key -> kind of the text it takes besides ('text', 'textarea'), for options that take one
    inputs: dict = field(default_factory=dict)

    @classmethod
    def read(cls, folder, name):
        '''The catalog *name* (e.g. ``mardmo-model-catalog``) from the questionnaire folder *folder*.'''
        folder = Path(folder)
        options, inputs = {}, {}
        for node in ET.parse(folder / 'optionsets.xml').getroot():
            if node.tag == 'option' and (node.findtext('additional_input') or 'False') not in ('', 'False'):
                inputs[_short(node.get(DC), OPTIONS)] = node.findtext('additional_input')
            if node.tag == 'optionset':
                options[node.get(DC)] = OptionSet(
                    key=_short(node.get(DC), OPTIONS),
                    provider=(node.findtext('provider_key') or '').strip(),
                    options=[_short(option.get(DC), OPTIONS)
                             for option in sorted(node.find('options'), key=lambda o: int(o.get('order') or 0))])
        conditions = {}
        for node in ET.parse(folder / 'conditions.xml').getroot():
            target = node.find('target_option')
            conditions[node.get(DC)] = Condition(
                key=_short(node.get(DC), TERMS + 'conditions/'),
                source=_short(node.find('source').get(DC), DOMAIN),
                relation=node.findtext('relation'),
                option=_short(target.get(DC), OPTIONS) if target is not None and target.get(DC) else None,
                text=node.findtext('target_text') or '')
        nodes = {node.get(DC): node for node in ET.parse(folder / f'{name}.xml').getroot()}

        def ordered(node, tag):
            container = node.find(f'{tag}s')
            children = [] if container is None else list(container)
            return [child.get(DC) for child in sorted(children, key=lambda c: int(c.get('order') or 0))]

        def build(uri, kind, parent=None):
            node = nodes[uri]
            attribute = node.find('attribute')
            element = Element(
                kind=kind, uri=uri, parent=parent,
                attribute=_short(attribute.get(DC), DOMAIN) if attribute is not None and attribute.get(DC) else None,
                is_collection=node.findtext('is_collection') == 'True',
                conditions=[conditions[c] for c in ordered(node, 'condition') if c in conditions],
                title=node.findtext("title[@lang='en']") or node.findtext("text[@lang='en']") or '')
            if kind == 'question':
                element.widget = node.findtext('widget_type') or ''
                element.value_type = node.findtext('value_type') or ''
                element.is_optional = node.findtext('is_optional') == 'True'
                element.optionsets = [options[o] for o in ordered(node, 'optionset') if o in options]
                return element
            # A page or question set: its question sets and questions, in their order
            container = []
            for tag, child_kind in (('questionset', 'questionset'), ('question', 'question')):
                holder = node.find(f'{tag}s')
                for child in (holder if holder is not None else []):
                    container.append((int(child.get('order') or 0), child.get(DC), child_kind))
            element.children = [build(child_uri, child_kind, element)
                                for _, child_uri, child_kind in sorted(container)]
            return element

        catalog_node = next(node for node in nodes.values() if node.tag == 'catalog')
        pages = [build(page, 'page') for section in ordered(catalog_node, 'section')
                 for page in ordered(nodes[section], 'page')]
        return cls(name=name, pages=pages, conditions=conditions, inputs=inputs)

    def elements(self):
        for page in self.pages:
            yield from page.walk()

    def questions(self):
        return [element for element in self.elements() if element.kind == 'question']

    def question(self, attribute):
        '''The question of the attribute key *attribute* (e.g. ``formulation/name``); fails unless exactly one.'''
        found = [question for question in self.questions() if question.attribute == attribute]
        assert len(found) == 1, f'{self.name}: {len(found)} questions with attribute {attribute}'
        return found[0]

    def page(self, attribute):
        '''The page of the attribute key *attribute* (e.g. ``formulation``).'''
        found = [page for page in self.pages if page.attribute == attribute]
        assert len(found) == 1, f'{self.name}: {len(found)} pages with attribute {attribute}'
        return found[0]


def outline(catalog):
    '''The catalog as indented text: what the generator's descriptions must cover.'''
    lines = []
    for element in catalog.elements():
        depth = len(element.path) - 1
        flags = ['collection'] if element.is_collection else []
        if element.kind == 'question':
            flags.append(element.widget)
            if element.providers:
                flags.append('provider ' + ','.join(element.providers))
            elif element.options:
                flags.append(f'{len(element.options)} options: ' + ', '.join(o.rsplit('/', 1)[-1] for o in element.options))
            if element.is_optional:
                flags.append('optional')
        if element.conditions:
            flags.append('if ' + ' and '.join(f'{c.source} {c.relation} {c.option or c.text}' for c in element.conditions))
        kind = {'page': 'P', 'questionset': 'S', 'question': 'Q'}[element.kind]
        lines.append(f'{"  " * depth}{kind} {element.key}  [{"; ".join(flags)}]')
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    print(outline(Catalog.read(sys.argv[1], sys.argv[2])))
