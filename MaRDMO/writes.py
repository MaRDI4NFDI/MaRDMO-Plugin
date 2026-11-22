'''MaRDMO's own writes of questionnaire values.

- :func:`value_editor` creates or updates one value.
- :func:`batched_writes` commits them in batches, :func:`commit_writes`
  before every request to an external service.
- :func:`internal_write` marks them as MaRDMO's, so the pre-save router
  skips the validators meant for user input.
'''
import sys

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import connection, transaction
from rdmo.domain.models import Attribute
from rdmo.options.models import Option
from rdmo.projects.models import Value


# Set while MaRDMO itself writes values (hydration, publication lookup, ID
# write-back); the pre-save router skips validators then, since they are meant
# for user input and imported data is checked by preview, checks and export
_INTERNAL_WRITE = ContextVar('mardmo_internal_write', default=False)


@contextmanager
def internal_write():
    '''Mark the values saved inside this block as written by MaRDMO itself.'''
    token = _INTERNAL_WRITE.set(True)
    try:
        yield
    finally:
        _INTERNAL_WRITE.reset(token)


def is_internal_write():
    '''Return ``True`` while MaRDMO itself is writing values (see :func:`internal_write`).'''
    return _INTERNAL_WRITE.get()


# Set inside batched_writes(): the open transaction (or None) and the
# attributes already looked up in this block
_WRITE_BATCH = ContextVar('mardmo_write_batch', default=None)


@contextmanager
def batched_writes():
    '''Commit MaRDMO's own writes in batches instead of one transaction per value.

    Adding an entry from the MaRDI Portal writes hundreds of values, which
    otherwise means hundreds of commits.  Inside this block, the writes of
    :func:`value_editor` are collected in one transaction, which is committed
    before every request to an external service (see :func:`commit_writes`)
    and at the end of the block.  The database is therefore never locked
    while MaRDMO waits for the network.  If the block raises, the writes
    since the last commit are rolled back.

    On SQLite every value is still committed on its own: SQLite locks the
    whole database, and a transaction that reads before it writes fails
    with "database is locked" when another user saves in between.

    Attributes looked up by URI are also remembered until the block ends.
    A nested block (e.g. a handler deleting further values) joins the
    outer one.
    '''
    if _WRITE_BATCH.get() is not None:
        yield
        return
    batch = {'atomic': None, 'attributes': {}}
    token = _WRITE_BATCH.set(batch)
    try:
        yield
    except BaseException:
        _close_transaction(batch, sys.exc_info())
        raise
    else:
        _close_transaction(batch)
    finally:
        _WRITE_BATCH.reset(token)


def _close_transaction(batch, exc_info=(None, None, None)):
    '''Commit (or, with *exc_info*, roll back) the open transaction of *batch*.'''
    atomic = batch['atomic']
    if atomic is not None:
        batch['atomic'] = None
        atomic.__exit__(*exc_info)


def commit_writes():
    '''Commit the writes collected by :func:`batched_writes` so far.

    Called before every request to an external service.  Does nothing
    outside :func:`batched_writes`.
    '''
    batch = _WRITE_BATCH.get()
    if batch is not None:
        _close_transaction(batch)


def _begin_write():
    '''Open the transaction of the current :func:`batched_writes` block, if needed.'''
    batch = _WRITE_BATCH.get()
    if batch is not None and batch['atomic'] is None and connection.vendor != 'sqlite':
        atomic = transaction.atomic()
        atomic.__enter__()
        batch['atomic'] = atomic


def get_attribute(uri):
    '''Return the :class:`~rdmo.domain.models.Attribute` with *uri*.

    Inside :func:`batched_writes` each attribute is looked up only once.

    Raises:
        Attribute.DoesNotExist: If there is no attribute with *uri*.
    '''
    batch = _WRITE_BATCH.get()
    if batch is None:
        return Attribute.objects.get(uri=uri)
    attributes = batch['attributes']
    if uri not in attributes:
        attributes[uri] = Attribute.objects.get(uri=uri)
    return attributes[uri]


def value_editor(project, uri, info):
    '''Create or update a single RDMO questionnaire :class:`~rdmo.projects.models.Value`.

    Looks up the :class:`~rdmo.domain.models.Attribute` for *uri* and calls
    ``Value.objects.update_or_create`` with whichever of the optional *info*
    keys are present.

    Args:
        project: RDMO project instance that owns the value.
        uri:     Full attribute URI (``BASE_URI + path``).
        info:    Dict of optional fields to write.  Recognised keys:

                 * ``text``             – free-text answer
                 * ``external_id``      – external identifier (e.g. Wikidata QID)
                 * ``option``           – option URI string (resolved to an
                   :class:`~rdmo.options.models.Option` instance)
                 * ``collection_index`` – position within a collection question
                 * ``set_index``        – page index within a repeating set
                 * ``set_prefix``       – parent set index for nested sets

    Returns:
        Tuple ``(obj, created)`` as returned by ``update_or_create``.
    '''
    attribute_object = get_attribute(uri)
    # Prepare the defaults dictionary
    defaults = {
        'project': project,
        'attribute': attribute_object,
    }

    if info.get('text') is not None:
        defaults['text'] = info['text']

    if info.get('external_id') is not None:
        defaults['external_id'] = info['external_id']

    if info.get('option') is not None:
        defaults['option'] = Option.objects.get(uri=info['option'])

    # Prepare the fields for update_or_create
    update_fields = {
        'project': project,
        'snapshot': None,
        'attribute': attribute_object,
        'defaults': defaults
    }

    if info.get('collection_index') is not None:
        update_fields['collection_index'] = info['collection_index']

    if info.get('set_index') is not None:
        update_fields['set_index'] = info['set_index']

    if info.get('set_prefix') is not None:
        update_fields['set_prefix'] = info['set_prefix']

    # Update or create the value
    _begin_write()
    with internal_write():
        obj, created = Value.objects.update_or_create(**update_fields)

    return obj, created
