'''Compiled regular expressions shared across MaRDMO modules.

Two families of patterns are defined here, each in a lenient and a strict
variant:

QUDT identifier patterns
------------------------
- :data:`QUDT_ID_RE`        — lenient, used in pre-save validation
  (:mod:`~MaRDMO.validators`).  Accepts a single uppercase letter so that
  incremental typing is not rejected before the user has finished.
- :data:`QUDT_ID_STRICT_RE` — strict, used in the documentation checker
  (:mod:`~MaRDMO.checks.model`) and portal importer (:mod:`~MaRDMO.adders`).
  Requires at least two characters so that a lone capital letter is flagged as
  incomplete.

DOI patterns
------------
- :data:`DOI_RE`        — progressive, used in pre-save validation
  (:mod:`~MaRDMO.validators`).  Accepts every valid prefix character by
  character (``1``, ``10``, ``10.``, ``10.1234``, ``10.1234/``,
  ``10.1234/suffix``) so the user is not blocked while still typing.
- :data:`DOI_STRICT_RE` — strict, used in the documentation checker
  (:mod:`~MaRDMO.checks.workflow`).  Requires the complete
  ``10.NNNN/suffix`` form.

Single-line text pattern
------------------------
- :data:`LINE_BREAK_RE` — line breaks, which the MaRDI Portal rejects in
  text values.
'''

import re

# ---------------------------------------------------------------------------
# QUDT identifier patterns
# ---------------------------------------------------------------------------

QUDT_ID_RE = re.compile(r'^[A-Z][a-zA-Z_\-]*$')
'''Lenient QUDT ID pattern (pre-save).

Matches an uppercase letter optionally followed by letters, underscores, or
hyphens.  The trailing quantifier is ``*`` (zero or more) so that a single
capital letter — the very first character the user types — is accepted without
error.  The strict variant enforces at least one additional character.
'''

QUDT_ID_STRICT_RE = re.compile(r'^[A-Z][a-zA-Z_\-]+$')
'''Strict QUDT ID pattern (documentation checker and portal importer).

Same character set as :data:`QUDT_ID_RE` but requires at least one character
after the initial uppercase letter (``+`` instead of ``*``), ensuring that a
lone capital is rejected as an incomplete identifier.
'''

# ---------------------------------------------------------------------------
# DOI patterns
# ---------------------------------------------------------------------------

DOI_RE = re.compile(r'^1(0(\.\d*(/\S*)?)?)?$')
'''Progressive DOI pattern (pre-save).

Accepts the DOI string character-by-character as the user types:

- ``1``           — first character of the fixed prefix
- ``10``          — prefix so far
- ``10.``         — separator typed
- ``10.1234``     — registrant code being entered
- ``10.1234/``    — separator between prefix and suffix
- ``10.1234/abc`` — suffix in progress

This prevents the field from turning red before the user has finished typing.
Completeness (``10.NNNN/suffix``) is enforced by :data:`DOI_STRICT_RE` at
export time.
'''

DOI_STRICT_RE = re.compile(r'^10\.\d{4,}/\S+$')
'''Strict DOI pattern (documentation checker).

Requires the canonical ``10.NNNN/suffix`` form: the fixed prefix ``10.``,
at least four registrant digits, a ``/`` separator, and one or more non-
whitespace suffix characters.
'''

# ---------------------------------------------------------------------------
# Single-line text pattern
# ---------------------------------------------------------------------------

LINE_BREAK_RE = re.compile(r'[\n\r]')
'''Line breaks, which the MaRDI Portal rejects in text values.

Only visible line breaks are matched; tabs and other invisible whitespace
(also rejected by the portal) are replaced by spaces on export instead.

Used by the pre-save validator for textarea answers (:mod:`~MaRDMO.validators`),
the documentation checker (:mod:`~MaRDMO.checks.base`), and the preview templates.
'''

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------

URL_FORBIDDEN_CHARS_RE = re.compile(r'[<>"{}|\\^`\x00-\x1f\x7f]')
'''Characters that are never valid in a URL (and break SPARQL IRIs).

Whitespace is checked separately to give a more specific message.
'''

URL_HOST_RE = re.compile(r'^[^\s.]+(\.[^\s.]+)+$')
'''Host with at least one dot (``example.org``); IP addresses are handled separately.'''
