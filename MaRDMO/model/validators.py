'''Pre-save validators of the model catalogs, registered in ``model/catalog.py``.'''
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from ..getters import get_mathmoddb
from .constants import data_properties_check


def validate_properties(instance):
    '''Reject a property option that creates a mutually exclusive pair.

    Collects all property option URIs already saved for the same entity page
    (same attribute and ``set_prefix``), adds the incoming option, then checks
    every pair in ``data_properties_check``.  Raises on the first conflict found.

    Skips the check when no option is attached to the instance (e.g. text-only
    saves that happen to land on the same attribute URI).

    The current instance is excluded from the DB query so that update operations
    (where the row already exists) are evaluated against the new option only.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when the incoming option together with already-saved
            options contains a mutually exclusive pair from
            ``data_properties_check``.
    '''
    if not instance.option:
        return

    qs = instance.project.values.filter(
        snapshot   = None,
        attribute  = instance.attribute,
        set_prefix = instance.set_prefix,
    )
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)

    existing_uris = set(qs.values_list('option__uri', flat=True))
    existing_uris.add(instance.option.uri)

    mathmoddb = get_mathmoddb()
    for key_a, key_b in data_properties_check:
        entry_a = mathmoddb.get(key=key_a)
        entry_b = mathmoddb.get(key=key_b)
        if entry_a and entry_b:
            if entry_a['url'] in existing_uris and entry_b['url'] in existing_uris:
                raise ValidationError({
                    'text': [format_lazy(
                        _(
                            'Inconsistent properties: {a} and {b}'
                            ' cannot both be selected.'
                        ),
                        a=_(mathmoddb.get(key=key_a)['label']),
                        b=_(mathmoddb.get(key=key_b)['label']),
                    )]
                })
