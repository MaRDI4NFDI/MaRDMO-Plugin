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
:func:`~MaRDMO.helpers.replace_ids` gives them the item's new portal ID.
'''
import uuid

from django.db.models import Q
from rdmo.projects.models import Value
from rdmo.questions.models import Question, QuestionSet

from .optionsets import PROVIDERS

NOT_FOUND = 'not found'
# Text of the option NOT_FOUND in the ID dropdown of a page
NEW_ITEM = 'new item'
SOURCES = ('user', 'mardi', 'wikidata')

# Attribute URIs of the answers that hold an item's ID (see id_attributes)
_ID_ATTRIBUTES = set()


def new_user_id():
    '''Return a new ID for an item of the user's own.'''
    return f'user:{uuid.uuid4()}'


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

    Relation answers store "not found" for an own item until they hold the
    ID of its page (#100); until then both mean the same own item, which is
    known by its name and description.
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
    becomes a new ``user:`` ID: a new item.  On the ID of a page
    (:func:`id_attributes`) an answer that has a ``user:`` ID already keeps
    it, so selecting "new item" again does not make a new item; a portal
    item switched to "new item" is the template of a new one.  A relation
    only refers to an item: choosing "new" again is another new item.

    No other answer changes: a page switched to another item (own, portal
    or Wikidata) leaves the relations with the old one, and the checks
    report those without page.  The user decides once whether an item is
    on the portal; afterwards only the export changes IDs (see
    :func:`~MaRDMO.helpers.replace_ids`).

    Args:
        value: Unsaved :class:`~rdmo.projects.models.Value` of a MaRDMO catalog.
    '''
    if value.external_id != NOT_FOUND:
        return
    if value.attribute.uri in id_attributes() and value.pk:
        old = Value.objects.filter(pk=value.pk).values_list('external_id', flat=True).first()
        if is_user_id(old):
            value.external_id = old
            return
    value.external_id = new_user_id()


def item_key(identifier, name, description):
    '''Return what makes an item in an export the same item: ``(ID, name, description)``.

    The user's own items are the same item when name and description are:
    the same new programming language on two software pages, or a page and
    the relations to it that still store "not found" (see :func:`is_own_item`).
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
    relations.  A relation row left without target loses its relation type
    and assumptions too.

    Args:
        value: Deleted :class:`~rdmo.projects.models.Value` of a page's ID question.
    '''
    identifier = value.external_id
    if not is_item_id(identifier) or not value.attribute.uri.endswith('/id'):
        return
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
    (:func:`source_help`), the preview by the ID.
    '''
    return f'{name} ({description})' if description else name


# Tag of an option's source, by the prefix of its ID
_SOURCE_TAGS = {'mardi': 'mardi', 'wikidata': 'wikidata', 'user': 'project'}


def source_tag(tag):
    '''Return the grey markup of the source tag *tag* for an option's help.

    RDMO shows the help of an option in the open dropdown only, and drops
    CSS classes given to it, so the markup is MaRDMO's own.
    '''
    return f'<strong class="text-muted">[{tag}]</strong>'


def source_help(identifier):
    '''Return the help of a dropdown option for the item *identifier*: its source tag.

    ``[mardi]``, ``[wikidata]``, or ``[project]`` for an item of the user's
    own in the project; ``''`` for anything else.
    '''
    tag = _SOURCE_TAGS.get((identifier or '').split(':', 1)[0]) if is_item_id(identifier) else None
    return source_tag(tag) if tag else ''


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
