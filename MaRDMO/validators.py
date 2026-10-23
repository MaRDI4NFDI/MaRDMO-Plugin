'''Pre-save validators for MaRDMO questionnaire values.

Each validator receives an RDMO ``Value`` instance and raises
``rest_framework.exceptions.ValidationError`` when the value is rejected.
Validators are registered in ``builders.py`` via ``build_presave_validator_map``.

Provides:

- :func:`validate_value_format`      — rejects entries not matching ``Label (Description)``
- :func:`validate_short_description` — rejects descriptions longer than the maximum length
- :func:`validate_qudt_id`           — rejects QUDT IDs not matching the expected format
- :func:`validate_doi`               — rejects DOI text not matching the expected format
- :func:`validate_properties`        — rejects mutually exclusive data-property combinations
- :func:`validate_single_line`       — rejects line breaks in textarea answers exported as text

Shared rules, also used by the documentation checker (:mod:`~MaRDMO.checks`)
and the preview templates (:mod:`~MaRDMO.templatetags.mardmo_tags`), so that
all three always agree:

- :func:`short_description_problem` — what is wrong with a short description
- :func:`has_equivalence_sign`      — whether a defining formula contains ``≡``
'''

from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from .getters import get_mathmoddb, get_options
from .helpers import extract_parts
from .model.constants import data_properties_check
from .patterns import DOI_RE, LINE_BREAK_RE, QUDT_ID_RE

SHORT_DESCRIPTION_MAX_LENGTH = 2000

# Encodings of the equivalence sign accepted in defining formulas
# (MathML from the portal or LaTeX entered by users)
EQUIVALENCE_SIGNS = ('>≡</', '>&#x2261;</', '>&equiv;</', '\\equiv', '\\Equiv')


def short_description_problem(description, name):
    '''Return what is wrong with an entity's short description, or ``None``.

    Args:
        description: Short description text (may be empty or ``None``).
        name:        Name of the same entity.

    Returns:
        ``'missing'``, ``'too_long'`` (more than
        :data:`SHORT_DESCRIPTION_MAX_LENGTH` characters), ``'same_as_name'``,
        or ``None`` if the description is fine.
    '''
    if not description:
        return 'missing'
    if len(description) > SHORT_DESCRIPTION_MAX_LENGTH:
        return 'too_long'
    if description == name:
        return 'same_as_name'
    return None


def has_equivalence_sign(formula):
    '''Return ``True`` if *formula* contains an equivalence sign (``\\equiv`` or ``≡``).'''
    return isinstance(formula, str) and any(sign in formula for sign in EQUIVALENCE_SIGNS)


def validate_single_line(instance):
    '''Reject text containing line breaks.

    Registered for textarea answers (and textarea option inputs) that are
    exported as single-line text statements; the MaRDI Portal rejects line
    breaks in those values.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when ``instance.text`` contains a line break.
    '''
    if instance.text and LINE_BREAK_RE.search(instance.text):
        raise ValidationError({
            'text': [_(
                'Line breaks are not allowed here: the MaRDI Portal stores'
                ' this answer as single-line text.'
            )]
        })


def validate_value_format(instance):
    '''Reject values whose text cannot be parsed as ``Label (Description)``.

    Accepts empty text (field cleared), ``Label (Description)`` (user entry),
    and ``Label (Description) [source]`` (external entry).  Rejects anything
    else — unclosed parentheses, plain text without parentheses, etc. — because
    ``general.relation`` would silently ignore those anyway.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when ``instance.text`` is non-empty and
            ``extract_parts`` cannot identify a source (``source == ""``).
    '''
    if not instance.text:
        return
    source = extract_parts(instance.text)[2]
    if source == '':
        raise ValidationError({
            'text': [_('Wrong format. Expected: Label (Description)')]
        })


def validate_short_description(instance):
    '''Reject a short description that exceeds the maximum length.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when ``instance.text`` exceeds
            :data:`SHORT_DESCRIPTION_MAX_LENGTH` characters.
    '''
    if instance.text and len(instance.text) > SHORT_DESCRIPTION_MAX_LENGTH:
        raise ValidationError({
            'text': [format_lazy(
                _('Short description must not exceed {max_length} characters.'),
                max_length=SHORT_DESCRIPTION_MAX_LENGTH,
            )]
        })


def validate_qudt_id(instance):
    '''Reject a QUDT reference ID that does not match the expected format.

    The ID must start with an uppercase letter, optionally followed by letters,
    underscores, or hyphens (e.g. ``SpeedOfLight``, ``MassOfElectron``).
    A single uppercase letter is accepted to avoid false errors during incremental
    typing; completeness is enforced by the documentation checker.

    Skips validation when no option or no text is present — the option being
    set indicates the user has committed to a reference type; only then is the
    text format enforced.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when both ``instance.option`` and ``instance.text``
            are set and ``instance.text`` does not match
            ``^[A-Z][a-zA-Z_\\-]*$``.
    '''
    if not instance.option or not instance.text:
        return
    if not QUDT_ID_RE.match(instance.text):
        raise ValidationError({
            'text': [_(
                'Invalid QUDT ID. Must start with an uppercase letter'
                ' and contain only letters, underscores, or hyphens'
                ' (e.g. SpeedOfLight).'
            )]
        })


def validate_doi(instance):
    '''Reject a DOI that does not match the expected format.

    Validates incrementally as the user types: accepts ``1``, ``10``, ``10.``,
    ``10.1234``, ``10.1234/``, ``10.1234/suffix`` — each a valid prefix of a
    complete DOI.  Completeness (``10.NNNN/suffix``) is enforced by the
    documentation checker via a strict regex.

    Triggers only when the selected option is the DOI option or the
    ``YesText`` option (Data Set "To Publish") and text is non-empty.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when both ``instance.option`` and ``instance.text``
            are set, the option is a DOI-entry option, and ``instance.text``
            does not match ``^1(0(\\.\\d*(/\\S*)?)?)?$``.
    '''
    if not instance.option or not instance.text:
        return
    opts = get_options()
    if instance.option.uri not in (opts.get('DOI'), opts.get('YesText')):
        return
    if not DOI_RE.match(instance.text):
        raise ValidationError({
            'text': [_('Invalid DOI. Expected format: 10.XXXX/suffix (e.g. 10.1000/xyz123).')]
        })


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
                        a=mathmoddb.get(key=key_a)['label'],
                        b=mathmoddb.get(key=key_b)['label'],
                    )]
                })
