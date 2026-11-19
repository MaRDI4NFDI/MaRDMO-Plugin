'''The pages (tabs) of a documentation as the preview and the checks name them (#152).

A page is named by its tab, the name the user sees in the interview (e.g.
"F4"), and shown with the name of its item.  :func:`add_tab_names` writes
the tab and an anchor into every page of the answers; a relation to a page
becomes a :class:`PageRef`, which renders as a link to the page:
"Navier-Stokes equation (F4)".
'''
from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.html import format_html
from rdmo.projects.models import Value
from rdmo.questions.models import Page


def anchor(section, index):
    '''The HTML ID of the page *index* (set index) of *section*.'''
    return f'page-{section}-{index}'


@dataclass(frozen=True)
class PageRef:
    '''A relation to the page *index* (set index) of *section*: its item's name and the tab.'''
    section: str
    index: int
    name: str
    tab: str
    # The ID of the page's item; not part of what makes two references equal
    item: str = field(default='', compare=False)

    @property
    def portal(self):
        '''Whether the page's item is an item of the MaRDI Portal (#167: its gaps are hints).'''
        return self.item.startswith('mardi:')

    @property
    def anchor(self):
        return anchor(self.section, self.index)

    @property
    def label(self):
        '''The page as text: "Navier-Stokes equation (F4)".'''
        if self.name and self.tab:
            return f'{self.name} ({self.tab})'
        return self.name or self.tab or f'page {self.index + 1}'

    def __str__(self):
        '''The link to the page (safe HTML); the templates print a relation as it is.

        Django's templates turn a value into a string before escaping it, so
        the link is the string; :attr:`label` is the text.
        '''
        if self.name and self.tab:
            return format_html('<a href="#{}">{}</a> ({})', self.anchor, self.name, self.tab)
        return format_html('<a href="#{}">{}</a>', self.anchor, self.label)

    __html__ = __str__


def page_ref(section, index, entry):
    '''The :class:`PageRef` of the page *entry* (answers of page *index* of *section*).'''
    return PageRef(section, index, entry.get('Name') or '', entry.get('Tab') or '', str(entry.get('ID') or ''))


def page_refs(data, sections):
    '''``{ID: PageRef}`` of the pages of *sections* in *data*, searched in this order.

    Of two pages with one ID (a copied tab) the first is taken, as the checks
    name it.  A tab is also found by its placeholder (``tab:<section>:<n>``).
    '''
    from .ids import tab_placeholder  # pylint: disable=import-outside-toplevel
    refs = {}
    for section in sections:
        for index, entry in (data.get(section) or {}).items():
            if not isinstance(entry, dict):
                continue
            if entry.get('ID'):
                refs.setdefault(entry['ID'], page_ref(section, index, entry))
            # The links of a tab whose item was cleared (#186) refer to the tab; the
            # checks report its missing ID
            refs[tab_placeholder(section, index)] = page_ref(section, index, entry)
    return refs


def tab_names(project, sections):
    '''``{section: {set index: tab name}}`` of the pages of *sections* of *project*.'''
    from .constants import BASE_URI  # constants imports helpers, which imports this module
    uris = {f'{BASE_URI}domain/{section}': section for section in sections}
    names = {}
    for uri, index, text in Value.objects.filter(
        project=project, snapshot=None, set_prefix='', attribute__uri__in=list(uris),
    ).values_list('attribute__uri', 'set_index', 'text'):
        names.setdefault(uris[uri], {})[index] = text
    return names


def interview_urls(project, sections):
    '''``{section: URL}`` of the interview pages whose tabs are the pages of *sections*.

    RDMO opens a page of the interview, not one of its tabs, so the preview
    names the tab next to the link.  A section without such a page in the
    project's catalog has no URL.
    '''
    from .constants import BASE_URI  # constants imports helpers, which imports this module
    uris = {f'{BASE_URI}domain/{section}': section for section in sections}
    base = reverse('project_interview', args=[project.pk])
    urls = {}
    for page in (Page.objects.filter(attribute__uri__in=list(uris), sections__catalogs=project.catalog)
                 .select_related('attribute').order_by('pk').distinct()):
        urls.setdefault(uris[page.attribute.uri], f'{base}{page.pk}/')
    return urls


def add_tab_names(project, data):
    '''Write ``Tab`` (the tab name) and ``Anchor`` (the HTML ID) into every page of *data*.

    Args:
        project: RDMO project of the answers.
        data:    Top-level answers dict ``{section: {set index: page}}``; mutated in place.

    Returns:
        *data*.
    '''
    names = tab_names(project, [section for section, pages in data.items() if isinstance(pages, dict)])
    for section, pages in data.items():
        if not isinstance(pages, dict):
            continue
        for index, entry in pages.items():
            if isinstance(entry, dict):
                entry['Tab'] = names.get(section, {}).get(index, '')
                entry['Anchor'] = anchor(section, index)
    return data
