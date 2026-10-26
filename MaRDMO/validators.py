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
- :func:`validate_url`               — rejects URLs that can never become valid while typing
- :func:`validate_reference`         — DOI or URL check, depending on the selected option

Shared rules, also used by the documentation checker (:mod:`~MaRDMO.checks`)
and the preview templates (:mod:`~MaRDMO.templatetags.mardmo_tags`), so that
all three always agree:

- :func:`short_description_problem` — what is wrong with a short description
- :func:`has_equivalence_sign`      — whether a defining formula contains ``≡``
- :func:`url_problem`               — what is wrong with a complete URL
- :func:`url_typing_problem`        — progressive URL check while typing (pre-save)
'''

import ipaddress
from urllib.parse import urlsplit

from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from .getters import get_mathmoddb, get_options
from .helpers import extract_parts
from .model.constants import data_properties_check
from .patterns import DOI_RE, LINE_BREAK_RE, QUDT_ID_RE, URL_FORBIDDEN_CHARS_RE, URL_HOST_RE

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


URL_MAX_LENGTH = 500

# Schemes accepted for URLs: web pages, and additionally version-control and
# file-transfer schemes for source code repositories (as used on Wikidata)
WEB_URL_SCHEMES = ('http', 'https')
REPOSITORY_URL_SCHEMES = WEB_URL_SCHEMES + ('git', 'ssh', 'svn', 'cvs', 'bzr', 'ftp')


def url_schemes(option_uri):
    '''Return the URL schemes allowed for a reference/documentation option.

    Source code repository URLs may also use version-control schemes; every
    other URL must be a web address.
    '''
    if option_uri == get_options().get('SOURCECODE_URL'):
        return REPOSITORY_URL_SCHEMES
    return WEB_URL_SCHEMES


def _scheme_message(schemes):
    '''Return the "must start with" message for *schemes*.'''
    if schemes == WEB_URL_SCHEMES:
        return 'URL must start with http:// or https://'
    return 'URL must start with http://, https://, git://, ssh://, svn://, cvs://, bzr:// or ftp://'


def _common_url_problem(url):
    '''Problems that make a URL invalid no matter how it continues.'''
    if len(url) > URL_MAX_LENGTH:
        return f'URL must not be longer than {URL_MAX_LENGTH} characters'
    if any(char.isspace() for char in url):
        return 'URL must not contain spaces'
    if URL_FORBIDDEN_CHARS_RE.search(url):
        return 'URL contains characters that are not allowed (< > " { } | \\ ^ `)'
    return None


def url_problem(url, schemes=WEB_URL_SCHEMES):
    '''Return what is wrong with a complete URL, or ``None`` if it is valid.

    Used by the preview, the documentation checker, and the export.  Leading
    and trailing whitespace is ignored (it is trimmed on export).

    Args:
        url:     URL text (empty or ``None`` is not checked here).
        schemes: Allowed schemes, see :func:`url_schemes`.

    Returns:
        A message for the user, or ``None``.
    '''
    url = (url or '').strip()
    if not url:
        return None
    problem = _common_url_problem(url)
    if problem:
        return problem
    parts = urlsplit(url)
    if parts.scheme.lower() not in schemes or not url.lower().startswith(f'{parts.scheme.lower()}://'):
        return _scheme_message(schemes)
    try:
        host, _port = parts.hostname or '', parts.port
    except ValueError:
        return 'URL contains an invalid port'
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not URL_HOST_RE.match(host):
            return 'URL needs a domain such as example.org'
    return None


def url_typing_problem(url, schemes=WEB_URL_SCHEMES):
    '''Return what is wrong with a URL that is still being typed, or ``None``.

    Progressive variant of :func:`url_problem` for the pre-save validator:
    only rejects what can never become valid by typing on (spaces inside,
    forbidden characters, a beginning that cannot lead to an allowed scheme,
    excessive length), so ``h``, ``https:`` or ``https://exa`` are accepted.
    '''
    url = (url or '').strip()
    if not url:
        return None
    problem = _common_url_problem(url)
    if problem:
        return problem
    lowered = url.lower()
    if '://' in lowered:
        scheme = lowered.split('://', 1)[0]
        if scheme not in schemes:
            return _scheme_message(schemes)
    elif not any(f'{scheme}://'.startswith(lowered) for scheme in schemes):
        return _scheme_message(schemes)
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


def validate_url(instance):
    '''Reject a URL that can never become valid while it is being typed.

    Triggers only for the URL options (source code repository URL,
    described-at URL, documentation URL) with non-empty text; uses the
    progressive :func:`url_typing_problem`, completeness is enforced by the
    documentation checker and the export.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when the URL text can no longer become valid.
    '''
    if not instance.option or not instance.text:
        return
    opts = get_options()
    if instance.option.uri not in (opts.get('SOURCECODE_URL'), opts.get('DESCRIPTION_URL'), opts.get('URL')):
        return
    problem = url_typing_problem(instance.text, url_schemes(instance.option.uri))
    if problem:
        raise ValidationError({'text': [problem]})


def validate_reference(instance):
    '''Validate a reference or documentation answer: DOI or URL, depending on the option.

    Registered for questions whose options include both DOI and URL entries;
    each validator only reacts to its own options.
    '''
    validate_doi(instance)
    validate_url(instance)


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
