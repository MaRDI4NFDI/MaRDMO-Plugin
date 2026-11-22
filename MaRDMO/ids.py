'''Stable IDs of the items in a project.

Every item in a project has an ID: ``mardi:<QID>`` or ``wikidata:<QID>`` for
an item of the MaRDI Portal or Wikidata, ``user:<uuid>`` for an item of the
user's own.  The dropdowns offer "new item" (ID of a page) or the typed
label (relations) to add an own item, both with the option ID "not found";
before the answer is saved, :func:`assign_id` replaces it by a new ``user:``
ID (see ``router.py``), so "not found" is never stored as an ID.

Answers that refer to an item hold its ID: a relation holds the ID of the
item's page.  When the page's name or description changes, :func:`sync_text`
changes their text; when the page is deleted, :func:`remove_references`
removes them.  When the user switches a page to another item, they stay
with the old one (see :func:`assign_id`); after an export,
:func:`replace_ids` gives them the item's new portal ID.

The export takes every item of the answers once (:func:`unique_items`) and
afterwards finds the items it created (:func:`compare_items`).
'''
import html
import uuid
from urllib.parse import unquote

from django.db.models import Q
from rdmo.projects.models import Value
from rdmo.questions.models import Question, QuestionSet

from .optionsets import PROVIDERS
from .properties import find_reference
from .writes import internal_write

NOT_FOUND = 'not found'
# Text of the option NOT_FOUND in the ID dropdown of a page
NEW_ITEM = 'new item'
SOURCES = ('user', 'mardi', 'wikidata')

# A publication is selected by its identifier with a prefix (#158); for now the DOI.
# The option of a new publication has the ID NEW_DOI + DOI, which the router turns
# into a user: ID (assign_id)
DOI_PREFIX = 'doi:'
NEW_DOI = 'new:doi:'
# Links to a DOI that are dropped when pasted after the prefix
_DOI_LINKS = ('https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/', 'http://dx.doi.org/', 'doi.org/')

# Attribute URIs of the answers that hold an item's ID (see id_attributes)
_ID_ATTRIBUTES = set()


def new_user_id():
    '''Return a new ID for an item of the user's own.'''
    return f'user:{uuid.uuid4()}'


def part_id(kind, *keys):
    '''Return the ``user:`` ID of a new author or journal (*kind*) of a publication.

    The preview writes a publication's authors and journal again each time
    from its citation, so their ID is derived from the first of *keys* that
    is given (ORCID iD, zbMATH ID, Wikidata QID, name; ISSN, Wikidata QID,
    title): the same each time, and the same for the same author in two
    publications.
    '''
    key = next((key for key in keys if key and key != 'None'), '')
    return f'user:{uuid.uuid5(uuid.NAMESPACE_URL, f"mardmo/{kind}/{key}")}'


def is_user_id(identifier):
    '''Return ``True`` if *identifier* is the ID of an item of the user's own.'''
    return bool(identifier) and identifier.startswith('user:')


def is_item_id(identifier):
    '''Return ``True`` if *identifier* is an ID of the form ``<source>:<id>``.'''
    return bool(identifier) and identifier.split(':', 1)[0] in SOURCES and ':' in identifier


def is_portal_item(identifier):
    '''Return ``True`` if *identifier* is the ID of an item of the MaRDI Portal or Wikidata.'''
    return bool(identifier) and identifier.split(':', 1)[0] in ('mardi', 'wikidata') and ':' in identifier


def is_own_item(identifier):
    '''Return ``True`` for an item of the user's own: a ``user:`` ID or "not found".

    Answers never store "not found" (:func:`assign_id`); it is the ID of the
    workflow itself in the export (:func:`~MaRDMO.ids.unique_items`), and
    of the items of projects made before 0.8.0, which the checks report.
    '''
    return identifier == NOT_FOUND or is_user_id(identifier)


def id_attributes():
    '''Return the attribute URIs of the answers that hold an item's ID.

    These are the questions whose dropdown searches without the project's
    answers and offers "new item": the ID of every page (``<section>/id``)
    and the items entered on a page without one of their own (programming
    languages, CPU models, instruments, methods).  Read from the
    questionnaire once it is there.
    '''
    if not _ID_ATTRIBUTES:
        keys = [key for key, search in PROVIDERS.items() if search.not_found and search.answers is None]
        _ID_ATTRIBUTES.update(
            Question.objects.filter(optionsets__provider_key__in=keys, attribute__isnull=False)
            .values_list('attribute__uri', flat=True)
        )
    return _ID_ATTRIBUTES


def assign_id(value):
    '''Give the answer *value*, before it is saved, a real ID.

    "not found" (the option "new item", or the typed label of a relation)
    becomes a new ``user:`` ID: a new item, and so does the option of a new
    publication (``new:doi:<DOI>``, #158), whose DOI is kept on the answer
    (``mardmo_doi``) for the handler.  On the ID of a page
    (:func:`id_attributes`) an answer that has a ``user:`` ID already keeps
    it, so selecting "new item" again does not make a new item; a portal
    item switched to "new item" is the template of a new one.  A relation
    only refers to an item: choosing "new" again is another new item.

    The ID answer of a tab remembers its previous ID (``mardmo_old_id``):
    when the interview changes it, the answers that referred to the old
    item follow the tab (:func:`follow_tab`, #186).  It never takes another
    ``user:`` ID than its own: the ID dropdowns do not offer the project's
    own items, so that can only be the interview sending a copied tab's old
    ID again after MaRDMO gave the copy its own.

    Args:
        value: Unsaved :class:`~rdmo.projects.models.Value` of a MaRDMO catalog.
    '''
    if is_tab_id(value) and value.pk:
        old = Value.objects.filter(pk=value.pk).values_list('external_id', flat=True).first()
        value.mardmo_old_id = old
        if is_user_id(old) and is_user_id(value.external_id) and value.external_id != old:
            value.external_id = old
    if (value.external_id or '').startswith(NEW_DOI):
        # A new publication by its DOI (#158): a user: ID like "new item"; the DOI
        # goes on to the handler with the answer (publication.handlers)
        value.mardmo_doi = value.external_id[len(NEW_DOI):]
        value.external_id = NOT_FOUND
    if value.external_id != NOT_FOUND:
        return
    if value.attribute.uri in id_attributes() and value.pk:
        old = Value.objects.filter(pk=value.pk).values_list('external_id', flat=True).first()
        if is_user_id(old):
            value.external_id = old
            return
    value.external_id = new_user_id()


def tab_id_attributes():
    '''Return the attribute URIs of the ID answers of tabs (``<section>/id``).'''
    return {uri for uri in id_attributes() if uri.endswith('/id')}


def is_tab_id(value):
    '''Return ``True`` if *value* is the ID answer of a tab (the item of a page).'''
    return value.set_prefix == '' and value.attribute.uri in tab_id_attributes()


# The ID of the links of a tab whose item was cleared: tab:<section>:<set index>
PLACEHOLDER_PREFIX = 'tab:'


def tab_placeholder(section, set_index):
    '''The ID the links of tab *set_index* of *section* get while it has no item (#186).'''
    return f'{PLACEHOLDER_PREFIX}{section}:{set_index}'


def is_placeholder(identifier):
    '''Return ``True`` if *identifier* is the :func:`tab_placeholder` of a tab without item.'''
    return bool(identifier) and identifier.startswith(PLACEHOLDER_PREFIX)


def _placeholder_of(value):
    '''The :func:`tab_placeholder` of the tab whose ID answer is *value*.'''
    return tab_placeholder(value.attribute.uri.rsplit('/', 2)[-2], value.set_index)


def follow_tab(value):
    '''Let the answers that referred to the previous item of a tab refer to its new one (#186).

    Called when the interview saved the ID answer *value* of a tab with
    another item: a tab is the item, so its links follow it, whatever the
    switch (own item, MaRDI Portal, Wikidata; also a portal item made a new
    item from it).  The answers get the new ID, and for a portal or Wikidata
    item the text of the option chosen; a new item keeps the name and
    description of the tab, so the texts stay.  Written with ``update()``:
    an interview open on another page can still save them.

    Several tabs with the old item (a copied portal item, or the same item
    selected twice): its links belong to the first of them, so they follow
    only that one; a later tab, or a tab of another section, moves nothing.
    Saves outside the interview (imports, MaRDMO's own writes, snapshot
    rollbacks) do not call this.

    A tab whose item is cleared keeps its links on its
    :func:`tab_placeholder`, and the item chosen next takes them; deleting
    the tab removes them (:func:`remove_references`).

    Returns:
        The number of answers that now refer to the new item.
    '''
    old, new = getattr(value, 'mardmo_old_id', None), value.external_id
    if old == new:
        return 0
    if is_item_id(old) and not new:
        new = _placeholder_of(value)                    # cleared: the tab keeps its links
    elif not old and is_item_id(new):
        old = _placeholder_of(value)                    # chosen after clearing
    elif not (is_item_id(old) and is_item_id(new)):
        return 0
    others = Value.objects.filter(project=value.project_id, snapshot=None, set_prefix='',
                                  attribute__uri__in=tab_id_attributes(), external_id=old).exclude(pk=value.pk)
    if (others.filter(attribute=value.attribute, set_index__lt=value.set_index).exists()
            or others.exclude(attribute=value.attribute).exists()):
        return 0
    links = Value.objects.filter(project=value.project_id, snapshot=None, external_id=old).exclude(
        attribute__uri__in=id_attributes())
    if is_portal_item(new) and value.text:
        return links.update(external_id=new, text=value.text)
    return links.update(external_id=new)


def give_copies_their_ids(project_id):
    '''Give the copies of own items in project *project_id* IDs of their own (#186).

    Called after RDMO copied a tab, or took one over from another project:
    RDMO writes the copied answers without signals, so the copy has the ID
    of its original.  A copy of an own item is a new item: every tab of a
    section with the ``user:`` ID of an earlier tab gets a new one; the
    links stay with the original (the first tab).  A copy of a MaRDI Portal
    or Wikidata item keeps its ID: it shows that item, and the checks report
    both tabs as one item until the user decides.  Written with
    ``update()``; the interview shows the copy's old ID until the page is
    loaded again, and :func:`assign_id` keeps the new one if it sends the
    old one back.

    Returns:
        The number of tabs that got a new ID.
    '''
    seen, copies = set(), []
    for pk, attribute, external_id in (
            Value.objects.filter(project=project_id, snapshot=None, set_prefix='',
                                 attribute__uri__in=tab_id_attributes(), external_id__startswith='user:')
            .order_by('attribute_id', 'set_index', 'pk').values_list('pk', 'attribute_id', 'external_id')):
        if (attribute, external_id) in seen:
            copies.append(pk)
        seen.add((attribute, external_id))
    for pk in copies:
        Value.objects.filter(pk=pk).update(external_id=new_user_id())
    return len(copies)


def publication_doi(text):
    '''The DOI of the identifier *text* typed for a publication (``doi:10.1000/x``), or ``None``.

    The prefix is required (case does not matter); spaces around and a link
    pasted after the prefix (``doi:https://doi.org/10.1000/x``) are dropped.
    A link is percent-encoded (``%3C`` for ``<``, ``%23`` for ``#`` in old
    DOIs): its DOI is decoded.  The DOI itself is not checked:
    :func:`~MaRDMO.validators.doi_problem` does.
    '''
    prefix, separator, rest = (text or '').strip().partition(':')
    if not separator or prefix.strip().lower() != DOI_PREFIX[:-1]:
        return None
    doi = rest.strip()
    for link in _DOI_LINKS:
        if doi.lower().startswith(link):
            doi = unquote(doi[len(link):].strip())
            break
    return doi


def item_key(identifier, name, description):
    '''Return what makes an item in an export the same item: ``(ID, name, description)``.

    The user's own items are the same item when name and description are:
    the same new programming language on two software pages, or the same
    new author in two publications.
    '''
    return ('user' if is_own_item(identifier) else identifier, name, description)


# Relatant attribute URI -> (relatant URIs, other URIs) of its relation row (see relation_rows)
_ROWS = {}


def relation_rows():
    '''Return ``{relatant URI: (relatant URIs, other URIs)}`` of the relation rows of the questionnaire.

    A row is a block of the questionnaire with a relation type question
    (``…/relation``, ``…-relation``, ``…-relation-<n>``): the relation type,
    its targets (``…relatant…``) and, for specializations, assumptions, all
    answered with the same set prefix and set index.  Read from the
    questionnaire once it is there.
    '''
    if not _ROWS:
        for questionset in QuestionSet.objects.prefetch_related('questions__attribute'):
            uris = {question.attribute.uri for question in questionset.questions.all() if question.attribute}
            names = {uri: uri.rsplit('/', 1)[-1] for uri in uris}
            if not any('relation' in name and 'relatant' not in name for name in names.values()):
                continue
            relatants = frozenset(uri for uri, name in names.items() if 'relatant' in name)
            others = frozenset(uris - relatants)
            for uri in relatants:
                _ROWS[uri] = (relatants, others)
    return _ROWS


def remove_references(value):
    '''Remove the answers that refer to the item of a deleted page.

    Called when the ID answer *value* of a page was deleted.  If the page's
    tab is gone too (the tab was deleted, not only its ID cleared) and no
    other page has the item's ID (e.g. a copied tab), every answer in the
    project with this ID is deleted: relations, assumptions, publication
    relations; for a tab without item, those on its placeholder
    (:func:`follow_tab`).  A relation row left without target loses its
    relation type and assumptions too.

    Args:
        value: Deleted :class:`~rdmo.projects.models.Value` of a page's ID question.
    '''
    identifier = value.external_id
    if not value.attribute.uri.endswith('/id'):
        return
    if not is_item_id(identifier):
        # A tab without item: its links are on its placeholder (follow_tab)
        if not is_tab_id(value):
            return
        identifier = _placeholder_of(value)
    project = value.project_id
    tab = Value.objects.filter(project=project, snapshot=None, attribute__uri=value.attribute.uri[:-len('/id')],
                               set_prefix=value.set_prefix, set_index=value.set_index)
    pages = Value.objects.filter(project=project, snapshot=None, external_id=identifier,
                                 attribute__uri__in=id_attributes())
    if tab.exists() or pages.exists():
        return

    references = Value.objects.filter(project=project, snapshot=None, external_id=identifier).select_related('attribute')
    rows = {(reference.attribute.uri, reference.set_prefix, reference.set_index) for reference in references
            if reference.attribute.uri in relation_rows()}
    references.delete()

    for uri, set_prefix, set_index in rows:
        relatants, others = relation_rows()[uri]
        row = Value.objects.filter(project=project, snapshot=None, set_prefix=set_prefix, set_index=set_index)
        if not row.filter(attribute__uri__in=relatants).exists():
            row.filter(attribute__uri__in=others).delete()


def item_text(name, description):
    '''Return the text of an answer that refers to an item, as the dropdowns show it.

    ``"Label (Description)"``, ``"Label"`` without description.  The source
    is not part of it (#103): the dropdowns show it in the option's help
    (:func:`option_help`), the preview by the ID.
    '''
    return f'{name} ({description})' if description else name


# The source of an option (#142): the word of its badge, by the prefix of its ID, with
# the badge's background and text colours (light, with the word: colour alone is not
# accessible)
_SOURCE_TAGS = {'mardi': 'mardi', 'wikidata': 'wikidata', 'user': 'project', 'new': 'new', NOT_FOUND: 'new'}
_BADGES = {'mardi': ('#dbe9ff', '#1a3d7c'), 'wikidata': ('#dcf3e3', '#1e5e33'),
           'project': ('#fff1cc', '#7a5a00'), 'new': ('#ece3fb', '#4b2c83')}
# Hides the plain text of a laid-out option (RDMO shows the text, then the help); a browser
# without :has() shows both, the text stays readable
_HIDE_TEXT = ('<style>.interview-select-option:has(.mardmo-option) > span:first-child {display: none}'
              '.interview-select-option:has(.mardmo-option) > span.ml-10 {margin-left: 0}</style>')


def option_help(identifier, text):
    '''Return the help of a dropdown option for the item *identifier* with the text *text*: its layout (#142).

    A badge with the source (``mardi``, ``wikidata``, ``project`` for an
    item of the user's own in the project, ``new`` for a new item: typed in
    a relation, ``not found``, or a new publication, ``new:doi:…``), the
    label in bold and the description in grey italics on a second line.
    RDMO renders the help of an option as HTML in the open dropdown only,
    after its text; a CSS rule hides the text there.  The text stays
    ``"Label (Description)"``: it is what RDMO stores and shows in the
    filled field, and what screen readers announce.  ``''`` for an option
    without source (e.g. "new item").
    '''
    from .values import extract_parts# pylint: disable=import-outside-toplevel
    tag = _SOURCE_TAGS.get((identifier or '').split(':', 1)[0])
    if not tag or (identifier == NOT_FOUND and text == NEW_ITEM):
        return ''
    background, colour = _BADGES[tag]
    label, description, _ = extract_parts(text or '')
    layout = (f'<span class="mardmo-option"><span style="display:inline-block;background:{background};'
              f'color:{colour};border-radius:3px;padding:0 5px;margin-right:6px;font-size:80%;'
              f'vertical-align:1px">{tag}</span><span style="font-weight:600">{html.escape(label)}</span>')
    if description and description != 'No Description Provided!':
        layout += (f'<br><span style="color:#6c757d;font-style:italic;font-size:90%;margin-left:2px">'
                   f'{html.escape(description)}</span>')
    return f'{_HIDE_TEXT}{layout}</span>'


def sync_text(value):
    '''Give the answers that refer to a page's item the page's new name and description.

    Called when the name or short description *value* of a page was saved
    (or cleared) in the interview.  Every answer in the project with the
    page's ID gets the text of :func:`item_text`, except the ID answers of
    pages (the page's own shows "new item" for an own item).  Written with
    ``update()``: the answers keep their ``updated`` time, so an interview
    open on another page can still save them.

    Args:
        value: :class:`~rdmo.projects.models.Value` of a page's name or description.
    '''
    section, question = value.attribute.uri.rsplit('/', 1)
    if question not in ('name', 'description') or f'{section}/id' not in id_attributes():
        return
    # A publication's name and description are answers of its own tab, the
    # others' are answers of the page (set prefix = the page's set index)
    if value.set_prefix == '':
        index = value.set_index
    elif value.set_prefix.isdigit():
        index = int(value.set_prefix)
    else:
        return
    # The page's ID, name and description in one query
    page = {
        uri: (external_id, text) for uri, external_id, text in Value.objects.filter(
            Q(attribute__uri=f'{section}/id', set_prefix='', set_index=index)
            | Q(attribute__uri__in=[f'{section}/name', f'{section}/description'],
                set_prefix=value.set_prefix, set_index=value.set_index),
            project=value.project_id, snapshot=None,
        ).values_list('attribute__uri', 'external_id', 'text')
    }
    identifier = page.get(f'{section}/id', ('', ''))[0]
    name = page.get(f'{section}/name', ('', ''))[1]
    if not is_item_id(identifier) or not name:
        return
    texts = {uri: text for uri, (_, text) in page.items()}
    Value.objects.filter(project=value.project_id, snapshot=None, external_id=identifier).exclude(
        attribute__uri__in=id_attributes()
    ).update(text=item_text(name, texts.get(f'{section}/description')))


# Answer keys of a publication's parts: an item under them is an author or a
# journal (#118), which the export creates with their own statements
PART_KINDS = {'author': 'author', 'journal': 'journal'}


def unique_items(data, title = None):
    '''Collect all unique items referenced anywhere in *data*.

    Recursively walks the nested answers dict and returns every sub-dict
    that contains an ``ID`` key exactly once.  An optional workflow *title*
    item is prepended as ``Item0000000000``.

    Args:
        data:  Top-level answers dict.
        title: Optional workflow title string.  When provided, a placeholder
               item for the workflow itself is added first.

    Returns:
        Tuple ``(items, dependency)`` where *items* maps ``"Item<n>"`` keys to
        ``{ID, Name, Description, orcid, zbmath, issn}`` dicts (with ``kind``
        ``author`` or ``journal`` for the authors and journals of
        publications, see :data:`PART_KINDS`) and *dependency*
        maps the same keys to empty sets (populated later by
        :class:`~MaRDMO.payload.GeneratePayload`).
    '''
    # Set up Item Dict and track seen Items
    items = {}
    dependency = {}
    seen_items = {}
    # Add Workflow Item
    if title:
        triple = (
            *item_key('not found', title, data.get('general', {}).get('objective', '')),
            '', '', '', None
        )
        items[f'Item{str(0).zfill(10)}'] = {
            'ID': 'not found',
            'Name': title,
            'Description': data.get('general', {}).get('objective', '')
        }
        seen_items[triple] = f'Item{str(0).zfill(10)}'
        dependency.update({f'Item{str(0).zfill(10)}': set()})
    # Add Workflow Component Items
    def search(subdict, kind=None):
        '''Search unique Items; *kind* is the kind of the publication part they are in.'''
        if isinstance(subdict, dict) and 'ID' in subdict:
            triple = (
                *item_key(subdict.get('ID', ''), subdict.get('Name', ''), subdict.get('Description', '')),
                subdict.get('orcid', ''),
                subdict.get('zbmath', ''),
                subdict.get('issn', ''),
                kind
            )
            if triple not in seen_items:
                item = f'Item{str(len(items)).zfill(10)}'  # Create unique key
                items[item] = {
                    'ID': subdict.get('ID', ''),
                    'Name': triple[1],
                    'Description': triple[2],
                    'orcid': triple[3],
                    'zbmath': triple[4],
                    'issn': triple[5]
                }
                if kind:
                    items[item]['kind'] = kind
                seen_items[triple] = item
                dependency.update({item: set()})
            # All user: IDs of the item, to give them its portal ID after the export
            if is_user_id(subdict['ID']):
                user_ids = items[seen_items[triple]].setdefault('user_ids', [])
                if subdict['ID'] not in user_ids:
                    user_ids.append(subdict['ID'])
        if isinstance(subdict, dict):
            for key, value in subdict.items():
                if isinstance(value, dict):
                    search(value, PART_KINDS.get(key, kind))
    search(data)
    _add_publication_dois(data, items, seen_items)
    return items, dependency


def _add_publication_dois(data, items, seen_items):
    '''Give the items of the publication pages of *data* their DOI (``doi``), if they have one (#158).

    The duplicate check finds publications on the MaRDI Portal by it
    (:func:`~MaRDMO.duplicates.look_up`).
    '''
    from .getters import get_options  # pylint: disable=import-outside-toplevel
    option = get_options()['DOI']
    for page in (data.get('publication') or {}).values():
        if not isinstance(page, dict) or not page.get('ID'):
            continue
        doi = find_reference(page.get('reference'), option)
        key = seen_items.get((*item_key(page['ID'], page.get('Name', ''), page.get('Description', '')),
                              page.get('orcid', ''), page.get('zbmath', ''), page.get('issn', ''), None))
        if doi and doi[1] and key:
            items[key].setdefault('doi', doi[1])


def compare_items(old, new, wikidata_qid_prop=None):
    """Return the items that got a QID by the export, by their payload key (``Item<n>``).

    Compares the ``id`` field of every ``Item*`` key: entries that had no id
    before posting (``old[key]['id']`` is falsy) and have one afterwards are
    collected together with the original external ID and the new QID.
    Items still without id (export aborted before they were posted) are
    skipped.

    The original external ID is inferred from the item's statements: items
    that carry a Wikidata QID external-id statement are tagged as
    ``wikidata:<QID>``; all others are tagged as ``user``, with the
    ``user:`` IDs the item had in the project (``user_ids`` of the payload
    entry).

    Args:
        old:                Deep copy of the payload dict taken *before* posting.
        new:                Payload dict *after* posting (ids filled in by Wikibase).
        wikidata_qid_prop:  Property ID string for the Wikidata QID property
                            (e.g. ``'P123'``), used to detect Wikidata-sourced
                            items.  Pass ``get_properties().get('Wikidata QID')``.

    Returns:
        Dict mapping payload keys to ``{'label': …, 'description': …,
        'old_id': <original external id>, 'new_qid': <assigned QID>,
        'class': <class>, 'user_ids': [<user: IDs>]}``.
    """

    created = {}
    for key, value in old.items():
        if key.startswith('Item') and not value['id'] and new[key].get('id'):
            item = new[key]
            label = item['payload']['item']['labels']['en']
            description = item['payload']['item'].get('descriptions', {}).get('en', '')

            # Detect wikidata items by presence of the Wikidata QID statement.
            old_id = 'user'
            if wikidata_qid_prop:
                for stmt in value.get('statements', []):
                    if stmt[0] == wikidata_qid_prop and stmt[1] == 'external-id':
                        old_id = f'wikidata:{stmt[2]}'
                        break

            created[key] = {
                'label':    label,
                'description': description,
                'old_id':   old_id,
                'new_qid':  item['id'],
                'class':    old[key].get('class', ''),
                'user_ids': old[key].get('user_ids', []),
            }
    return created


def replace_ids(project, created):
    """Update RDMO project Values after a successful portal export.

    For every newly created MaRDI Portal item, every
    :class:`~rdmo.projects.models.Value` in *project* that holds its old ID
    gets the new ``mardi:<QID>`` identifier:

    - **Wikidata items**: matched by their ``wikidata:<QID>``.
    - **Items of the user's own**: matched by their ``user:`` IDs (all of
      them, if the export made one item of several, see :func:`unique_items`).

    The text becomes the exported item's ``"Label (Description)"``
    (:func:`~MaRDMO.ids.item_text`).

    Args:
        project:  RDMO project instance whose Values should be updated.
        created:  Dict as returned by :func:`compare_items` —
                  ``{key: {'label': ..., 'description': ..., 'old_id': ..., 'new_qid': ...,
                  'user_ids': [...]}}``.
    """

    # Wikidata items: one bulk query per export, matched by QID
    wikidata_map = {
        info['old_id']: (f"mardi:{info['new_qid']}", item_text(info['label'], info['description']))
        for info in created.values()
        if info['old_id'].startswith('wikidata:')
    }
    if wikidata_map:
        for v in Value.objects.filter(
            project=project, snapshot=None, external_id__in=wikidata_map
        ).select_related('attribute'):
            v.external_id, v.text = wikidata_map[v.external_id]
            with internal_write():
                v.save()

    # Items of the user's own: matched by ID, written with update() so an
    # interview open on another page can still save
    for info in created.values():
        if info.get('user_ids'):
            Value.objects.filter(
                project=project, snapshot=None, external_id__in=info['user_ids']
            ).update(
                external_id=f"mardi:{info['new_qid']}",
                text=item_text(info['label'], info['description']),
            )
