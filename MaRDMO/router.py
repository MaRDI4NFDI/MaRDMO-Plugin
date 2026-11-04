'''Django signal router that dispatches RDMO value saves and deletes to MaRDMO handlers.

On every ``value_created`` or ``value_updated`` signal the post-save router checks
whether the project's catalog is a MaRDMO catalog and, if so, looks up the
saved attribute URI in ``HANDLER_MAP`` to call the matching handler method.

On every Django ``post_delete`` signal on ``Value`` the post-delete router does the
same lookup in ``DELETE_HANDLER_MAP``.  Using ``post_delete`` (rather than RDMO's
custom ``value_deleted``) ensures the handler fires for both individual REST
deletions and set deletions via RDMO's ``delete_set``, which calls
``value.delete()`` directly.

Both maps are assembled once at startup via
:func:`~MaRDMO.builders.build_post_save_handler_set` and
:func:`~MaRDMO.builders.build_post_delete_handler_set`.

Before a ``Value`` is saved through the interview, the pre-save router looks up
the attribute URI in ``PRESAVE_VALIDATOR_MAP`` and calls the matching validator,
which may raise ``ValidationError`` to reject the value and surface an error in
the UI.  Saves from anywhere else (project import, management commands,
MaRDMO's own writes) are not validated there; preview, checks and export
check all values.  ``PRESAVE_VALIDATOR_MAP`` is assembled explicitly by
:func:`~MaRDMO.builders.build_presave_validator_map`.

All maps are assembled once at startup.

Provides:

- ``HANDLER_MAP``           — ``{catalog: {uri: handler}}`` dispatch dict for saves
- ``DELETE_HANDLER_MAP``    — ``{catalog: {uri: handler}}`` dispatch dict for deletes
- ``PRESAVE_VALIDATOR_MAP`` — ``{catalog: {uri: validator}}`` dispatch dict for pre-save validation
- ``mardmo_router_post_save``   — receiver wired to ``value_created`` and ``value_updated``
- ``mardmo_router_post_delete`` — receiver wired to Django's ``post_delete`` on ``Value``
- ``mardmo_router_pre_save``    — receiver wired to Django's ``pre_save`` on ``Value``
'''

from contextvars import ContextVar

from django.core.signals import request_finished, request_started
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.urls import Resolver404, resolve
from rdmo.projects.models import Value
from rdmo.projects.signals import value_created, value_updated
from .constants import (
    CATALOG_MODEL_NAME,
    CATALOG_MODEL_BASICS_NAME,
    CATALOG_ALGORITHM_NAME,
    CATALOG_WORKFLOW_NAME,
)
from .helpers import batched_writes, is_internal_write
from .builders import (
    build_post_save_handler_set,
    build_post_delete_handler_set,
    build_presave_validator_map,
)

HANDLER_MAP           = build_post_save_handler_set()
DELETE_HANDLER_MAP    = build_post_delete_handler_set()
PRESAVE_VALIDATOR_MAP = build_presave_validator_map()

_MARDMO_CATALOGS = (
    CATALOG_MODEL_NAME,
    CATALOG_MODEL_BASICS_NAME,
    CATALOG_ALGORITHM_NAME,
    CATALOG_WORKFLOW_NAME,
)


def _catalog_name(instance):
    '''Return the short catalog slug for *instance*, or ``None`` if not a MaRDMO catalog.'''
    catalog = getattr(instance.project, "catalog", None)
    if not catalog or not str(catalog).endswith(_MARDMO_CATALOGS):
        return None
    return str(catalog).rsplit("/", maxsplit=1)[-1]


# Path of the request handled in the current context, set by request_started
_request_path = ContextVar('mardmo_request_path', default=None)

# The interview saves answers through RDMO's project value API (create, update)
_INTERVIEW_VALUE_VIEWS = {
    'v1-projects:project-value-list',
    'v1-projects:project-value-detail',
}


@receiver(request_started)
def _remember_request_path(sender, environ=None, scope=None, **kwargs):  # pylint: disable=unused-argument
    '''Store the path of the request that is about to be handled (WSGI or ASGI).'''
    if environ is not None:
        path = environ.get('PATH_INFO')
    elif scope is not None:
        path, root = scope.get('path', ''), scope.get('root_path', '')
        path = path[len(root):] if root and path.startswith(root) else path
    else:
        path = None
    _request_path.set(path)


@receiver(request_finished)
def _forget_request_path(sender, **kwargs):  # pylint: disable=unused-argument
    '''Clear the stored request path once the response is finished.'''
    _request_path.set(None)


def _is_interview_save():
    '''Return ``True`` if the current request is the interview saving an answer.

    Project imports, set copies, management commands and background threads
    save values too; those are not validated here (the values are checked by
    preview, checks and export), so an old project with values that newer
    rules reject can still be imported.
    '''
    path = _request_path.get()
    if not path:
        return False
    try:
        match = resolve(path)
    except Resolver404:
        return False
    return match.view_name in _INTERVIEW_VALUE_VIEWS


def _is_snapshot_rollback(instance):
    '''Return ``True`` if *instance* is a snapshot value being restored as a live value.

    RDMO's ``Snapshot.rollback`` re-saves each snapshot value with
    ``snapshot=None``; the stored row still carries the snapshot at that point.
    '''
    return (
        instance.pk is not None
        and Value.objects.filter(pk=instance.pk, snapshot__isnull=False).exists()
    )


@receiver(value_created, sender=Value)
@receiver(value_updated, sender=Value)
def mardmo_router_post_save(sender, instance, update_fields=None, **kwargs):  # pylint: disable=unused-argument
    """Post-save router: dispatch Value saves to the correct MaRDMO handler.

    Connected to both ``value_created`` and ``value_updated`` signals.
    Looks up the project catalog and attribute URI in ``HANDLER_MAP`` and
    calls the matching handler, if any.

    Args:
        sender:        Signal sender class (``Value``).
        instance:      The saved :class:`~rdmo.projects.models.Value` instance.
        update_fields: Fields that were updated (unused; present for signal compatibility).
        **kwargs:      Additional signal keyword arguments (unused).
    """
    if not instance or instance.snapshot_id:
        return

    catalog_name = _catalog_name(instance)
    if not catalog_name:
        return

    attr_uri = getattr(instance.attribute, "uri", None)
    if not attr_uri:
        return

    handler = HANDLER_MAP.get(catalog_name, {}).get(attr_uri)
    if handler:
        with batched_writes():
            handler(instance)


@receiver(post_delete, sender=Value)
def mardmo_router_post_delete(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """Post-delete router: dispatch Value deletions to the correct MaRDMO handler.

    Connected to Django's ``post_delete`` signal on ``Value``.  This covers both
    individual REST deletions (via ``perform_destroy``) and set deletions (via
    RDMO's ``delete_set``, which calls ``value.delete()`` directly without sending
    ``value_deleted``).
    Looks up the project catalog and attribute URI in ``DELETE_HANDLER_MAP`` and
    calls the matching handler, if any.

    Args:
        sender:   Signal sender class (``Value``).
        instance: The deleted :class:`~rdmo.projects.models.Value` instance.
        **kwargs: Additional signal keyword arguments (unused).
    """
    if not instance or instance.snapshot_id:
        return

    catalog_name = _catalog_name(instance)
    if not catalog_name:
        return

    attr_uri = getattr(instance.attribute, "uri", None)
    if not attr_uri:
        return

    handler = DELETE_HANDLER_MAP.get(catalog_name, {}).get(attr_uri)
    if handler:
        with batched_writes():
            handler(instance)


@receiver(pre_save, sender=Value)
def mardmo_router_pre_save(sender, instance=None, **kwargs):  # pylint: disable=unused-argument
    """Pre-save router: validate Value text before it is written to the database.

    Connected to Django's ``pre_save`` signal on ``Value``.
    Only answers saved through the interview are validated; skips fixture
    loads, snapshots, non-MaRDMO catalogs, attributes with no registered
    validator, and every other save (see :func:`_is_interview_save`).  Calls
    the matching validator from ``PRESAVE_VALIDATOR_MAP``, which raises
    ``ValidationError`` to reject malformed input.

    Args:
        sender:   Signal sender class (``Value``).
        instance: The ``Value`` instance about to be saved.
        **kwargs: Additional signal keyword arguments (includes ``raw`` for
                  fixture loads).
    """
    # Fixture loads and MaRDMO's own writes are not validated (see below)
    if kwargs.get('raw') or is_internal_write():
        return

    # Snapshot copies and rollbacks restore values that were valid when saved
    if not instance or instance.snapshot_id:
        return

    catalog_name = _catalog_name(instance)
    if not catalog_name:
        return

    attr_uri = getattr(instance.attribute, 'uri', None)
    if not attr_uri:
        return

    validator = PRESAVE_VALIDATOR_MAP.get(catalog_name, {}).get(attr_uri)
    # Validators check input from the interview; everything else (imports,
    # MaRDMO's own writes, snapshot rollbacks) is checked by preview, checks
    # and export
    if validator and _is_interview_save() and not _is_snapshot_rollback(instance):
        validator(instance)
