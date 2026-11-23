'''The parts of the payload: texts and values cleaned for the portal, request bodies and URLs.

Pure functions: :class:`~MaRDMO.payload.GeneratePayload` assembles the
payload from them.
'''
import re

from ..components.validators import normalize_formula

# Datatypes whose values the portal stores as single-line text
TEXT_TYPES = ('string', 'external-id', 'url', 'URL', 'monolingualtext')

# Placeholder of an item of the export, replaced by its QID while posting
ITEM_KEY_RE = re.compile(r'^Item\d{10}$')
# Invisible whitespace the portal rejects; replaced by spaces on export
INVISIBLE_WHITESPACE_RE = re.compile(r'[\t\v\f]')


def text_of(value):
    '''Return the text part of a plain or monolingual-text value, else ``None``.'''
    if isinstance(value, dict):
        value = value.get('text')
    return value if isinstance(value, str) else None


def clean_text(text):
    '''Replace tabs with spaces and strip leading/trailing whitespace.

    The portal rejects both; neither changes the meaning of the text.
    Line breaks are left alone (blocked by the validator and the checks).
    '''
    return INVISIBLE_WHITESPACE_RE.sub(' ', text).strip()


def strip_text(value, data_type):
    '''Apply :func:`clean_text` to text values and put formulas on one line.

    Values of other datatypes are returned unchanged.
    '''
    if data_type == 'math' and isinstance(value, str):
        return normalize_formula(value)
    if data_type not in TEXT_TYPES:
        return value
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict) and isinstance(value.get('text'), str):
        return {**value, 'text': clean_text(value['text'])}
    return value


def quantity_amount(text):
    '''Return *text* as a Wikibase quantity amount (``"08"`` → ``"+8"``, ``" 1.50"`` → ``"+1.50"``).

    Strips whitespace and leading zeros of plain decimals; anything else is
    passed through with a ``+`` so that :meth:`~MaRDMO.payload.GeneratePayload.validate_identifiers`
    reports it instead of the portal rejecting it during the upload.
    '''
    text = str(text or '').strip()
    integer, dot, fraction = text.partition('.')
    if integer.isascii() and integer.isdigit() and (not dot or (fraction.isascii() and fraction.isdigit())):
        integer = integer.lstrip('0') or '0'
        return f"+{integer}{dot}{fraction}"
    return f"+{text}"


def items_url(url):
    '''Return the Wikibase REST API endpoint URL for creating new items on the Wikibase at *url*.'''
    return f'{url}/w/rest.php/wikibase/v1/entities/items'


def statement_url(url, item):
    '''Return the Wikibase REST API endpoint URL for adding statements to *item*.

    Args:
        url:  Base URL of the Wikibase.
        item: Wikibase QID string (e.g. ``"Q42"``).
    '''
    return f'{url}/w/rest.php/wikibase/v1/entities/items/{item}/statements'


def alias_url(url, item):
    '''Return the Wikibase REST API endpoint URL for adding English aliases to *item*.

    Args:
        url:  Base URL of the Wikibase.
        item: Wikibase QID string (e.g. ``"Q42"``).
    '''
    return f'{url}/w/rest.php/wikibase/v1/entities/items/{item}/aliases/en'


def build_item(url, identifier, label, description, statements = None):
    '''Build the payload dict for a new or existing Wikibase item.

    Args:
        url:         Base URL of the Wikibase.
        identifier:  Existing Wikibase QID (empty string for new items).
        label:       English label string.
        description: English description string.
        statements:  Optional list of statement triples; defaults to ``[]``.

    Returns:
        Dict with keys ``id``, ``url``, ``label``, ``description``,
        and ``statements``.
    '''
    # Empty Statements if none provided
    if statements is None:
        statements = []
    if description == "No Description Provided!":
        description = ""
    label = clean_text(label) if isinstance(label, str) else label
    description = clean_text(description) if isinstance(description, str) else description
    # Build Item
    item = {'id': identifier,
            'url': items_url(url),
            'label': label,
            'description':  description,
            'statements': statements}
    return item


def build_statement(identifier, content, data_type = "wikibase-item", qualifiers = None):
    '''Build the Wikibase REST API statement payload dict.

    Args:
        identifier:  Wikibase property ID string (e.g. ``"P31"``).
        content:     Statement value (QID, string, or typed literal).
        data_type:   Wikibase datatype string (default ``"wikibase-item"``).
        qualifiers:  Optional list of qualifier dicts; defaults to ``[]``.

    Returns:
        Dict in the shape expected by the Wikibase REST API
        ``POST .../statements`` endpoint.
    '''
    # Empty Qualifiers if none provided
    if qualifiers is None:
        qualifiers = []
    # Build Statement
    statement = {"statement":
                    {"property":
                        {"id": identifier,
                         "data_type": data_type},
                         "value":
                            {"type": "value",
                             "content": content},
                         "qualifiers": qualifiers
                    }
                }
    return statement


def build_alias(alias):
    '''Wrap *alias* in the ``{"aliases": …}`` payload dict expected by the API.

    Args:
        alias: List of alias strings.

    Returns:
        Dict ``{"aliases": alias}``.
    '''
    aliases_dict = {
      "aliases": alias
    }
    return aliases_dict


def normalize_aliases(aliases_dict: dict) -> list[str]:
    '''Convert a ``{index: alias}`` dict to a sorted, deduplicated list of strings.

    Args:
        aliases_dict: Dict mapping integer-like keys to alias strings.

    Returns:
        List of non-blank alias strings in ascending key order.
    '''
    return [
        clean_text(a) for _, a in sorted(aliases_dict.items())
        if isinstance(a, str) and a.strip()
    ]


def build_qualifier(identifier, data_type, content):
    '''Build a single-qualifier list for use in :meth:`~MaRDMO.payload.GeneratePayload.add_answer`.

    Args:
        identifier: Wikibase property ID string for the qualifier (e.g. ``"P3"``).
        data_type:  Wikibase datatype string for the qualifier value.
        content:    Qualifier value (QID, string, or typed literal).

    Returns:
        Single-element list containing the qualifier dict, or an empty
        list when a text value is empty after stripping whitespace.
    '''
    content = strip_text(content, data_type)
    if data_type in TEXT_TYPES and not text_of(content):
        return []
    # Build Qualifer
    qualifier = [{"property":
                    {"id": identifier,
                     "data_type": data_type},
                     "value": 
                        {"type": "value",
                         "content": content}
                }]
    return qualifier
