'''The IDs of a project's items while it is answered (#186, #198).

Before an answer is saved, :func:`assign_id` replaces "not found" by a new
``user:`` ID (see ``router.py``), so "not found" is never stored as an ID.

Answers that refer to an item hold its ID: a relation holds the ID of the
item's page.  When the page's name or description changes, :func:`sync_text`
changes their text; when the page is deleted, :func:`remove_references`
removes them.  When the interview switches a tab to another item, they follow
the tab (:func:`follow_tab`); a copied tab of an own item gets an ID of its
own (:func:`give_copies_their_ids`).  The rules of the IDs themselves are in
:mod:`MaRDMO.core.ids`.
'''
from django.db.models import Q
from rdmo.projects.models import Value
from rdmo.questions.models import Question, QuestionSet

from ..core.ids import NEW_DOI, NOT_FOUND, is_item_id, is_portal_item, is_user_id, item_text, new_user_id, tab_placeholder
from ..core.searches import PROVIDERS


# Attribute URIs of the answers that hold an item's ID (see id_attributes)
_ID_ATTRIBUTES = set()


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
