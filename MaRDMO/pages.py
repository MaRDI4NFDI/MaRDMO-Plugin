'''The pages (tabs) of a documentation as the preview and the checks name them (#152).

A page is named by its tab, the name the user sees in the interview (e.g.
"F4"), and shown with the name of its item.  :func:`add_tab_names` writes
the tab and an anchor into every page of the answers; a relation to a page
becomes a :class:`PageRef`, which renders as a link to the page:
"Navier-Stokes equation (F4)".

Preview, checks and export read the name and description of an item from
its page (:func:`link_to_pages`); own items without a page get a generic
description (:func:`describe_items_without_page`), and publications with
the same name and description their DOI (:func:`distinguish_publications`).
'''
from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.html import format_html
from rdmo.projects.models import Value
from rdmo.questions.models import Page

from .constants import BASE_URI
from .ids import is_own_item
from .properties import find_reference


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


def pages_by_id(data):
    '''Return ``{ID: page entry}`` of every item page in the answers *data*.

    A page is an entry of a section (``data[section][index]``) with an ``ID``;
    of two pages with one ID (a copied tab) the first.
    '''
    pages = {}
    for section in data.values():
        if isinstance(section, dict):
            for entry in section.values():
                if isinstance(entry, dict) and entry.get('ID'):
                    pages.setdefault(entry['ID'], entry)
    return pages


def distinguish_publications(data):
    '''Give publications with the name and description of another publication of *data* their own (#183).

    The name and description of a publication are its citation's, and the
    user cannot change them; two publications may have the same (a short
    title, a description such as "scientific article published in 2020").
    The export would make them one item, and the MaRDI Portal takes only one
    item per name and description.  So every one but the first of a name
    and description gets its DOI in the description ("… (DOI 10.…)"), a
    Wikidata publication without DOI its Wikidata QID.  Pages with the same
    DOI (or ID) are one publication and keep theirs (the checks report
    them); publications of the MaRDI Portal are not changed.  Runs before
    :func:`link_to_pages`, so the relations to them follow.

    Args:
        data: Top-level answers dict; mutated in place (``Description``,
              and ``Distinguished`` on the pages changed).

    Returns:
        *data*.
    '''
    from .getters import get_options  # pylint: disable=import-outside-toplevel
    option = get_options()['DOI']
    groups = {}
    for index in sorted(data.get('publication') or {}):
        page = data['publication'][index]
        if isinstance(page, dict) and page.get('ID') and page.get('Name') and not page['ID'].startswith('mardi:'):
            groups.setdefault((page['Name'], page.get('Description') or ''), []).append(page)
    for (_, description), pages in groups.items():
        first = None
        for page in pages:
            doi = find_reference(page.get('reference'), option)
            if doi and doi[1]:
                identifier = ('DOI', doi[1])
            elif page['ID'].startswith('wikidata:'):
                identifier = ('Wikidata QID', page['ID'].split(':', 1)[1])
            else:
                identifier = None
            same = identifier[1].upper() if identifier else page['ID']
            if first is None or same == first:
                first = same if first is None else first
                continue
            if identifier:
                page['Description'] = f'{description} ({identifier[0]} {identifier[1]})'
                page['Distinguished'] = True
    return data


def link_to_pages(data):
    '''Give every answer that refers to an item page the page's name and description.

    A relation holds the ID of its item and the text it was selected with;
    the page is what the user edits.  So preview, checks and export show and
    use the page's current name and description, also after it was renamed.
    Answers that refer to no page (inline items, portal items without page)
    keep theirs.

    Args:
        data: Top-level answers dict; mutated in place.

    Returns:
        *data*.
    '''
    pages = pages_by_id(data)

    def link(entry):
        for value in entry.values():
            if not isinstance(value, dict):
                continue
            page = pages.get(value.get('ID'))
            if page is not None and page is not value:
                value['Name'] = page.get('Name', '')
                value['Description'] = page.get('Description', '')
            link(value)

    for page in list(pages.values()):
        link(page)
    return data


# Own items entered on a page without a page of their own, and their generic
# description: {(section, answer key): description}.  Answers of these keys
# that refer to a page (e.g. tasks in the algorithm catalog) are not changed.
GENERIC_DESCRIPTIONS = {
    ('software', 'programminglanguage'): 'programming language',
    ('hardware', 'cpu'): 'cpu model',
    ('processstep', 'MRelatant'): 'experimental method',
    ('processstep', 'IRelatant'): 'instrument',
    ('processstep', 'RFRelatant'): 'academic discipline',
    ('algorithm', 'PRelatant'): 'algorithmic task',
}


def describe_items_without_page(data):
    '''Give the user's own items without page the generic description of their kind.

    The user types only the label of a new programming language, CPU model,
    method, instrument, research field or algorithmic task where it has no
    page (#129); the description comes from :data:`GENERIC_DESCRIPTIONS`, so
    preview, checks and export show and send "Label (programming language)".
    Not stored in the project.

    Args:
        data: Top-level answers dict; mutated in place.

    Returns:
        *data*.
    '''
    pages = pages_by_id(data)

    def describe(answers, description):
        for value in answers.values():
            if not isinstance(value, dict):
                continue
            if 'ID' not in value:
                describe(value, description)    # several per row (methods)
            elif is_own_item(value['ID']) and value['ID'] not in pages:
                value['Description'] = description

    for (section, key), description in GENERIC_DESCRIPTIONS.items():
        for entry in data.get(section, {}).values():
            if isinstance(entry, dict) and isinstance(entry.get(key), dict):
                describe(entry[key], description)
    return data
