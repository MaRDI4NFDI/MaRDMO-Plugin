'''Stable IDs of the items in a project.

Every item in a project has an ID: ``mardi:<QID>`` or ``wikidata:<QID>`` for
an item of the MaRDI Portal or Wikidata, ``user:<uuid>`` for an item of the
user's own.  The dropdowns offer "not found" (ID of a page) or the typed
label (relations) to add an own item; before the answer is saved,
:func:`assign_id` replaces "not found" by a new ``user:`` ID (see
``router.py``), so "not found" is never stored as an ID.

Answers that refer to an item hold its ID: a relation holds the ID of the
item's page.  When the ID of a page changes (e.g. an own item is found on
the portal), :func:`move_id` gives the answers the new one.
'''
import uuid

from rdmo.projects.models import Value
from rdmo.questions.models import Question

from .optionsets import PROVIDERS

NOT_FOUND = 'not found'
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
    answers and offers "not found": the ID of every page (``<section>/id``)
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

    "not found" becomes a new ``user:`` ID: a new item.  On the ID of a page
    (:func:`id_attributes`) an answer that has a ``user:`` ID already keeps
    it, so selecting "not found" again does not make a new item; and if the
    item becomes known on the portal (see :func:`same_item`), the answers
    that refer to the old ID get the new one (:func:`move_id`).  A relation
    only refers to an item: choosing "new" again is another new item, and a
    relation changed to another item moves nothing.

    Args:
        value: Unsaved :class:`~rdmo.projects.models.Value` of a MaRDMO catalog.
    '''
    if value.attribute.uri not in id_attributes():
        if value.external_id == NOT_FOUND:
            value.external_id = new_user_id()
        return
    old = Value.objects.filter(pk=value.pk).values_list('external_id', flat=True).first() if value.pk else None
    if value.external_id == NOT_FOUND:
        value.external_id = old if is_user_id(old) else new_user_id()
    if same_item(old, value.external_id):
        # Another answer with the old ID is the same item on another page (or
        # entered again); the references stay with it
        keeps_old = Value.objects.filter(
            project=value.project, snapshot=None, external_id=old, attribute__uri__in=id_attributes()
        ).exclude(pk=value.pk).exists()
        if not keeps_old:
            move_id(value.project, old, value.external_id, exclude=value.pk)


def same_item(old, new):
    '''Return ``True`` if a page whose ID changes from *old* to *new* stays the same item.

    That is when only its ID becomes known: an own item is found on the
    portal or Wikidata (or exported), or a Wikidata item is on the portal
    now.  Otherwise the page becomes another item and the answers stay with
    the old one: a portal item switched to "not found" is the template of a
    new item, and one portal item changed to another may be a correction or
    another item.
    '''
    if not (is_item_id(old) and is_item_id(new)) or old == new:
        return False
    source = new.split(':', 1)[0]
    return (is_user_id(old) and source in ('mardi', 'wikidata')) or (
        old.startswith('wikidata:') and source == 'mardi')


def move_id(project, old, new, exclude=None):
    '''Give every answer in *project* that holds the ID *old* the ID *new*.

    Saved with ``update()``: the answers keep their ``updated`` time, so an
    interview open on another page can still save them.

    Args:
        project: RDMO project instance.
        old:     ID the answers hold now.
        new:     ID they get.
        exclude: Primary key of an answer to leave alone (the one being saved).

    Returns:
        Number of answers changed.
    '''
    return (
        Value.objects.filter(project=project, snapshot=None, external_id=old)
        .exclude(pk=exclude)
        .update(external_id=new)
    )


def item_key(identifier, name, description):
    '''Return what makes an item in an export the same item: ``(ID, name, description)``.

    The user's own items are the same item when name and description are:
    the same new programming language on two software pages, or a page and
    the relations to it that still store "not found" (see :func:`is_own_item`).
    '''
    return ('user' if is_own_item(identifier) else identifier, name, description)
