'''Reading MaRDMO's pages in tests: what a user sees, not the exact markup.

A page is parsed into a small tree (Python's ``html.parser``), so a test
finds an element by its ID, class or tag and reads its text, its links or
whether a button is disabled.  Another order of attributes, an added class
or other whitespace does not break it::

    page = preview_page(client, documentation)
    assert export_button(page) == 'disabled'
    problems = element(page, id='export-problems')
    assert 'Missing Short Description' in text(problems)
    assert ('conservation law ...', '#page-formulation-1') in links(problems)

The parser is tolerant like a browser: a piece cut out of a page, or an end
tag without its start, is read as far as it goes.
'''
from dataclasses import dataclass, field
from html.parser import HTMLParser

from django.template.loader import render_to_string

from MaRDMO import main
from MaRDMO.catalogs import catalog_of
from MaRDMO.getters import get_item_url

PREVIEW_URL = '/projects/{}/export/wikibase/'
# Elements without content
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
# Elements whose content is not text the user reads
_HIDDEN = {'script', 'style', 'template'}
# Elements that start a new line: their text is separated from the text around them
_BLOCKS = {'br', 'p', 'li', 'ul', 'ol', 'div', 'section', 'details', 'summary', 'fieldset', 'legend',
           'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'table', 'tr', 'td', 'th'}


@dataclass
class Node:
    '''An element: its tag, attributes (``None`` for one without value) and children (nodes and text).'''
    name: str
    attributes: dict = field(default_factory=dict)
    children: list = field(default_factory=list)


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('#root')
        self.open = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.open[-1].children.append(node)
        if tag not in _VOID:
            self.open.append(node)

    def handle_startendtag(self, tag, attrs):
        self.open[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        # Close up to the matching element; an end tag without its start is ignored
        for depth in range(len(self.open) - 1, 0, -1):
            if self.open[depth].name == tag:
                del self.open[depth:]
                return

    def handle_data(self, data):
        self.open[-1].children.append(data)


def tree(page):
    '''*page* (HTML, or a node already parsed) as a :class:`Node`.'''
    if isinstance(page, Node):
        return page
    parser = _Parser()
    parser.feed(page)
    parser.close()
    return parser.root


def _walk(node):
    for child in node.children:
        if isinstance(child, Node):
            yield child
            yield from _walk(child)


def attribute(node, name):
    '''The attribute *name* of *node*: its value, ``''`` for one without value, ``None`` if it is missing.'''
    if name not in node.attributes:
        return None
    value = node.attributes[name]
    return '' if value is None else value


def elements(page, tag=None, id=None, cls=None, **attributes):  # noqa: A002 (as in HTML)
    '''The elements of *page* with the *tag*, *id*, class *cls* and *attributes* (``None``: any).

    An attribute with a dash is given with an underscore (``aria_describedby``).
    '''
    found = []
    for node in _walk(tree(page)):
        if tag is not None and node.name != tag:
            continue
        if id is not None and attribute(node, 'id') != id:
            continue
        if cls is not None and cls not in (attribute(node, 'class') or '').split():
            continue
        if any(attribute(node, name.replace('_', '-')) != value for name, value in attributes.items()):
            continue
        found.append(node)
    return found


def element(page, tag=None, id=None, cls=None, **attributes):  # noqa: A002
    '''The one element of *page* that :func:`elements` finds; fails if there is none or more than one.'''
    found = elements(page, tag, id, cls, **attributes)
    assert len(found) == 1, f'{len(found)} elements {tag or ""}#{id or ""}.{cls or ""} {attributes or ""}'
    return found[0]


def text(page):
    '''The text of *page* (HTML or node) as the user reads it: one space between words, no scripts.'''
    parts = []

    def collect(node):
        for child in node.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.name not in _HIDDEN:
                block = child.name in _BLOCKS
                if block:
                    parts.append(' ')
                collect(child)
                if block:
                    parts.append(' ')
    node = tree(page)
    if node.name not in _HIDDEN:
        collect(node)
    return ' '.join(''.join(parts).split())


def links(page):
    '''``[(text, href)]`` of the links of *page* (HTML or node), in their order.'''
    return [(text(node), attribute(node, 'href')) for node in elements(page, tag='a')]


def export_button(page):
    '''The state of the preview's export button: ``'enabled'``, ``'disabled'``, or ``None`` without one.

    The button is the submit button of the export form that is not *Cancel*.
    '''
    buttons = [node for form in elements(page, tag='form', cls='mardmo-export-form')
               for node in elements(form, tag='input', type='submit') if attribute(node, 'name') != 'cancel']
    if not buttons:
        return None
    assert len(buttons) == 1, f'{len(buttons)} export buttons'
    return 'disabled' if attribute(buttons[0], 'disabled') is not None else 'enabled'


def preview_page(client, project, language=None):
    '''The preview of *project* as the user gets it (the export page, GET), in *language* if given.'''
    headers = {'HTTP_ACCEPT_LANGUAGE': language} if language else {}
    response = client.get(PREVIEW_URL.format(project.pk), **headers)
    assert response.status_code == 200, response.status_code
    return response.content.decode()


def export_page(client, project, language=None):
    '''What the export of *project* answers (the export page, POST), in *language* if given.'''
    headers = {'HTTP_ACCEPT_LANGUAGE': language} if language else {}
    return client.post(PREVIEW_URL.format(project.pk), {}, **headers)


def rendered_preview(project, step=None):
    '''``(answers, html)``: the template of *project*'s catalog with its answers, without request and checks.

    *step* is passed to ``get_post_data`` (``'preview'`` looks up what the
    preview shows of portal items).
    '''
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, options = provider.get_post_data(step) if step else provider.get_post_data()
    html = render_to_string(catalog_of(project).template, {
        'answers': answers, 'option': options, 'title': project.title,
        'mardiURI': get_item_url('mardi'), 'wikidataURI': get_item_url('wikidata')})
    return answers, html
