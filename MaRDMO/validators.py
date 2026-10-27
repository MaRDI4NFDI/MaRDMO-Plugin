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
- :func:`validate_swmath`            — rejects swMATH IDs that are not numbers
- :func:`validate_reference`         — DOI, URL or swMATH check, depending on the selected option
- :func:`validate_archive_year`      — rejects archival years that can never become four digits
- :func:`validate_count`             — rejects counts (nodes, CPUs, cores) that are not whole numbers
- :func:`validate_data_size`         — rejects data sizes that are not numbers (whole for items)

Shared rules, also used by the documentation checker (:mod:`~MaRDMO.checks`)
and the preview templates (:mod:`~MaRDMO.templatetags.mardmo_tags`), so that
all three always agree:

- :func:`short_description_problem` — what is wrong with a short description
- :func:`has_equivalence_sign`      — whether a defining formula contains ``≡``
- :func:`normalize_formula`         — a formula as one line, as checked and exported
- :func:`formula_comment_problem`   — a ``%`` comment that joining the lines would break
- :func:`url_problem`               — what is wrong with a complete URL
- :func:`url_typing_problem`        — progressive URL check while typing (pre-save)
- :func:`doi_problem`               — what is wrong with a complete DOI
- :func:`swmath_problem`            — what is wrong with a swMATH work ID
- :func:`archive_year_problem`      — what is wrong with a complete archival year
- :func:`count_problem`             — what is wrong with a count (whole number ≥ 1)
- :func:`size_problem`              — what is wrong with a data size
'''

import ipaddress
from urllib.parse import urlsplit

from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from .getters import get_mathmoddb, get_options
from .helpers import extract_parts
from .model.constants import data_properties_check
from .patterns import (
    DOI_RE, DOI_STRICT_RE, LINE_BREAK_RE, QUDT_ID_RE, SWMATH_ID_RE,
    COUNT_RE, COUNT_STRICT_RE, FORMULA_WHITESPACE_RE, SIZE_RE, SIZE_STRICT_RE, TEX_COMMENT_RE,
    URL_FORBIDDEN_CHARS_RE, URL_HOST_RE, YEAR_RE, YEAR_STRICT_RE,
)

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


def _looks_like_link(text):
    '''Return ``True`` if *text* looks like a pasted link instead of a bare identifier.'''
    lowered = text.lower()
    return lowered.startswith(('http:', 'https:', 'www.', 'doi:')) or '.org/' in lowered


def doi_problem(doi):
    '''Return what is wrong with a complete DOI, or ``None`` if it is valid.

    Used by the preview, the documentation checker, and the export (the
    pre-save validator uses the progressive :data:`~MaRDMO.patterns.DOI_RE`).
    '''
    doi = (doi or '').strip()
    if not doi:
        return None
    if _looks_like_link(doi):
        return 'Enter only the DOI (e.g. 10.1000/xyz123), not the link'
    if not DOI_STRICT_RE.match(doi):
        return 'DOI must have the form 10.XXXX/suffix (e.g. 10.1000/xyz123)'
    return None


def swmath_problem(swmath_id):
    '''Return what is wrong with a swMATH work ID, or ``None`` if it is valid.

    swMATH IDs are numbers; the same rule applies while typing and when
    complete, so it is used by all four places (pre-save, preview, checks,
    export).
    '''
    swmath_id = (swmath_id or '').strip()
    if not swmath_id:
        return None
    if _looks_like_link(swmath_id) or '/' in swmath_id:
        return 'Enter only the swMATH number (e.g. 7554), not the link'
    if not SWMATH_ID_RE.match(swmath_id):
        return 'swMATH ID must be a number (e.g. 7554)'
    return None


def archive_year_problem(year):
    '''Return what is wrong with a complete archival year, or ``None`` if it is valid.

    Used by the preview, the documentation checker, and the export (the
    pre-save validator uses the progressive :data:`~MaRDMO.patterns.YEAR_RE`).
    '''
    year = str(year or '').strip()
    if not year:
        return None
    if not YEAR_STRICT_RE.match(year):
        return 'Archival year must be a 4-digit year (e.g. 2030)'
    return None


def has_equivalence_sign(formula):
    '''Return ``True`` if *formula* contains an equivalence sign (``\\equiv`` or ``≡``).'''
    return isinstance(formula, str) and any(sign in formula for sign in EQUIVALENCE_SIGNS)


def normalize_formula(tex):
    '''Return *tex* as one line: line breaks and tabs become spaces, outer whitespace is removed.

    The MaRDI Portal rejects line breaks, tabs and leading/trailing whitespace
    in math values.  TeX reads a line break as a space, so the formula keeps
    its meaning (``\\\\`` line breaks are untouched), except after a ``%``
    comment, see :func:`formula_comment_problem`.  Used by the TeX check and
    the export.
    '''
    return FORMULA_WHITESPACE_RE.sub(' ', str(tex or '')).strip()


def formula_comment_problem(tex):
    '''Return what is wrong with a multi-line formula containing a ``%`` comment, or ``None``.

    A comment runs to the end of its line; once the lines are joined for the
    export it would hide the rest of the formula.  ``\\%`` (a percent sign)
    is fine.
    '''
    if isinstance(tex, str) and LINE_BREAK_RE.search(tex) and TEX_COMMENT_RE.search(tex):
        return 'contains a % comment, which would hide the rest of the formula (use \\% for a percent sign)'
    return None


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
    if _looks_like_link(instance.text.strip()):
        raise ValidationError({
            'text': [_('Enter only the DOI (e.g. 10.1000/xyz123), not the link.')]
        })
    if not DOI_RE.match(instance.text.strip()):
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


def validate_swmath(instance):
    '''Reject a swMATH work ID that is not a number.

    Triggers only for the swMATH option with non-empty text.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when the text is not a plain number.
    '''
    if not instance.option or not instance.text:
        return
    if instance.option.uri != get_options().get('SWMATH'):
        return
    problem = swmath_problem(instance.text)
    if problem:
        raise ValidationError({'text': [problem]})


def count_problem(value):
    '''Return what is wrong with a count (nodes, CPUs, cores, items), or ``None``.

    A count is a whole number of at least 1 without leading zeros.  Used by
    the preview, the documentation checker, and the export.
    '''
    text = str(value or '').strip()
    if not text:
        return None
    if not text.isascii() or not text.isdigit():
        return 'must be a whole number (e.g. 4)'
    if int(text) == 0:
        return 'must be at least 1'
    if not COUNT_STRICT_RE.match(text):
        return 'must not start with 0 (e.g. 8 instead of 08)'
    return None


def size_problem(value, integer=False):
    '''Return what is wrong with a data size, or ``None`` if it is valid.

    Args:
        value:   Size text.
        integer: ``True`` for the unit "items", which needs a whole number.
    '''
    if integer:
        return count_problem(value)
    text = str(value or '').strip()
    if not text:
        return None
    if ',' in text:
        return 'use a dot as decimal separator (e.g. 1.5)'
    if not SIZE_STRICT_RE.match(text):
        if SIZE_STRICT_RE.match(text.lstrip('0')) and text.lstrip('0')[:1] not in ('', '.'):
            return 'must not start with 0 (e.g. 7.5 instead of 07.5)'
        return 'must be a number (e.g. 12 or 1.5)'
    if float(text) == 0:
        return 'must be greater than 0'
    return None


def validate_count(instance):
    '''Reject a count (nodes, CPUs, cores) that can never become a whole number ≥ 1.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when the text contains anything but digits or starts with 0.
    '''
    text = (instance.text or '').strip()
    if text and not COUNT_RE.match(text):
        raise ValidationError({'text': [
            _('Enter a whole number of at least 1 without leading zeros (e.g. 4).')
        ]})


def validate_data_size(instance):
    '''Reject a data size that can never become valid for the selected unit.

    Whole numbers for the unit "items", otherwise decimals with a dot
    (``1.`` is accepted while typing).

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when the text cannot become a valid size.
    '''
    text = (instance.text or '').strip()
    if not instance.option or not text:
        return
    if instance.option.uri == get_options().get('items'):
        if not COUNT_RE.match(text):
            raise ValidationError({'text': [
                _('Enter the number of items as a whole number of at least 1 (e.g. 250).')
            ]})
        return
    if ',' in text:
        raise ValidationError({'text': [_('Use a dot as decimal separator (e.g. 1.5).')]})
    if not SIZE_RE.match(text):
        raise ValidationError({'text': [_('Enter the size as a number (e.g. 12 or 1.5).')]})


def validate_archive_year(instance):
    '''Reject an archival year that can never become a 4-digit year.

    Triggers only for the ``YesText`` option (Data Set "To Archive") with
    non-empty text; up to four digits are accepted while typing.

    Args:
        instance: RDMO ``Value`` instance about to be saved.

    Raises:
        ValidationError: when the text contains anything but up to four digits.
    '''
    if not instance.option or not instance.text:
        return
    if instance.option.uri != get_options().get('YesText'):
        return
    if not YEAR_RE.match(instance.text.strip()):
        raise ValidationError({
            'text': [_('Archival year must be a 4-digit year (e.g. 2030).')]
        })


def validate_reference(instance):
    '''Validate a reference or documentation answer: DOI, URL, or swMATH ID, depending on the option.

    Registered for questions whose options include several of these entries;
    each validator only reacts to its own options.
    '''
    validate_doi(instance)
    validate_url(instance)
    validate_swmath(instance)


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
