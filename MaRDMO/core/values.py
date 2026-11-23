'''Reading and converting the values of answers and external sources.

The text of an item answer (:func:`extract_parts`), the parts of SPARQL
results (:func:`split_value`), dates (:func:`date_format`,
:func:`date_precision`), qualifiers (:func:`process_qualifier`) and the
basic entries of the answer routing (:func:`basic_dict`, :func:`basic_list`).
'''
import re

from typing import Any, Callable, Optional

from .ids import is_own_item


def date_format(parts: list) -> str | None:
    """Return a date string as YYYY-MM-DDT00:00:00Z given a list of date parts.

    Tolerates the shapes external sources deliver: numbers or strings, a
    missing (``None``) part, or a part with trailing text such as
    ``"13T10:00:00Z"``.  The date ends at the first missing or unreadable
    part, so ``[2020, None]`` gives a year-only date; ``None`` is returned
    if not even the year is readable.
    """
    numbers = []
    for part in (parts or [])[:3]:
        match = re.match(r'\s*(\d+)', str(part)) if part is not None else None
        if not match:
            break
        numbers.append(int(match.group(1)))
    if not numbers:
        return None
    year, month, day = (numbers + [0, 0])[:3]
    return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"

def date_precision(date_str: str) -> int | None:
    """
    Return Wikibase precision based on a date string.
    '+YYYY' -> 9, '+YYYY-MM' -> 10, '+YYYY-MM-DD' -> 11.
    """
    if not date_str:
        return None

    # Remove leading + and split date/time
    date_only = date_str.lstrip('+').split('T')[0]  # 'YYYY-MM-DD' or shorter
    parts = date_only.split('-')

    year = parts[0]
    month = parts[1] if len(parts) > 1 else '00'
    day = parts[2] if len(parts) > 2 else '00'

    if year != '0000':
        if month != '00':
            if day != '00':
                return 11  # day precision
            return 10  # month precision
        return 9  # year precision
    return None


def split_value(
    data: dict,
    key: str,
    transform: Optional[Callable[[str], Any]] = None,
    object_role: Optional[Callable[[Any], bool]] = None,
) -> list:
    """
    Split ``data[key]['value']`` on ``' <|> '``. Optionally apply a transform
    to each element and filter the results with ``object_role``.

    The elements are sorted (relatants thereby by ID), as SPARQL's
    ``GROUP_CONCAT`` returns them in no fixed order.
    """
    if key not in data:
        return []

    raw = sorted(data.get(key, {}).get('value', '').split(" <|> "))

    parts = [part for part in raw if part]

    if transform is not None:
        parts = [transform(part) for part in parts]

    if object_role is not None:
        parts = [part for part in parts if object_role(part)]

    return parts

def basic_dict(value):
    '''Build a basic entity dict from an RDMO ``Value`` object.

    Extracts the label and description from the human-readable text of a
    relation answer and returns them together with the external ID.  The
    text of a portal item is ``"Label (Description)"``; the text of
    an own item is its label as typed (#129): an item with a page gets its
    page's name and description (:func:`~MaRDMO.pages.link_to_pages`), one without a
    generic description (:func:`~MaRDMO.pages.describe_items_without_page`).

    Args:
        value: An RDMO :class:`~rdmo.projects.models.Value` instance.

    Returns:
        Dict with keys ``ID``, ``Name``, and ``Description``.
    '''
    if is_own_item(value.external_id):
        label, description = value.text, ''
    else:
        label, description, _ = extract_parts(value.text)
    # Return Basic Dict
    return {
        'ID': value.external_id,
        'Name': label,
        'Description': description
    }

def basic_list(value):
    '''Build a two-element list ``[option_uri, text]`` from an RDMO ``Value``.

    Args:
        value: An RDMO :class:`~rdmo.projects.models.Value` instance.

    Returns:
        ``[value.option_uri, value.text]``
    '''
    # Return Basic List
    return [
        value.option_uri,
        value.text
    ]


def nested_set(data, path, entry):
    """Set ``data[path[0]][path[1]]…[path[-1]] = entry``, creating intermediate dicts.

    Args:
        data:  Root dict to update in place.
        path:  Sequence of keys describing the nested location.
        entry: Value to store at the leaf.
    """
    d = data
    for key in path[:-1]:
        d = d.setdefault(key, {})
    d[path[-1]] = entry

def extract_parts(string):
    '''Extract the label, description, and source tag from an ID question text string.

    Expected format: ``"Label (Description)"``; answers saved before 0.8.0
    may end with a source tag (``"Euler method (algorithm) [mardi]"``), which
    is stripped (#103).  Falls back gracefully when the format is incomplete.
    The source of an item is its ID's, not the text's.

    Args:
        string: Text of an answer that refers to an item.

    Returns:
        Tuple ``(label, description, source)`` of extracted string components.
        *source* defaults to ``"user"`` when the bracket suffix is absent but
        the string ends with ``)``.  A string without description (e.g. the
        label of a new item, ``"reaction rate"``) is all label:
        ``("reaction rate", "", "")``.
    '''
    # Step 1: Split the string at the last occurrence of ') [' to isolate source
    parts = string.rsplit(') [', 1)
    if len(parts) == 2:
        main_part, c = parts[0].strip(), parts[1].rstrip(']')
    else:
        main_part = parts[0].strip()
        if main_part.endswith(')'):
            main_part, c = main_part.rstrip(')'), "user"
        else:
            return main_part, "", ""
    # Step 2: Find the last whitespace outside brackets to split
    depth = 0
    split_index = -1
    for i, char in enumerate(main_part):
        if char in ('(', '['):
            depth += 1
        elif char in (')', ']'):
            depth -= 1
        elif char == ' ' and depth == 0:
            split_index = i  # Update split_index to last whitespace outside brackets
    if split_index != -1:
        a = main_part[:split_index].strip()
        b = main_part[split_index+1:].strip().lstrip('(')  # Strip any leading '('
    else:
        a, b = main_part, ""
    return a, b, c


def process_qualifier(value):
    '''Parse a compound qualifier string into a structured dict.

    The expected format is entries separated by ``' <<||>> '``, where each
    entry has the form ``"id || label || description"``.

    Args:
        value: Raw qualifier string from the questionnaire.

    Returns:
        Dict mapping integer index to ``{id, label, description, source}``.
    '''
    # Create Value Dictionary
    value_dict = {}
    # Get splitted Values
    value_splitted = value.split(' <<||>> ')
    for value_idx, value_text in enumerate(value_splitted):
        # Extract Value ID, Label, and Description
        value_id, value_label, value_description = value_text.split(' || ')
        # Get Value Source
        value_source, _ = value_id.split(':')
        # Add to dict
        value_dict.update({value_idx: {'id': value_id,
                                       'label': value_label,
                                       'description': value_description,
                                       'source': value_source}})
    return value_dict


def replace_in_dict(d, target, replacement):
    '''Recursively replace all occurrences of *target* with *replacement* in *d*.

    Traverses nested dicts and lists, replacing string values that equal
    *target*.  Used after a Wikibase item is created to substitute the
    temporary ``Item<n>`` placeholder with the real QID.

    Args:
        d:           Dict, list, string, or scalar to process.
        target:      String to search for.
        replacement: Replacement string.

    Returns:
        A new structure with replacements applied (strings are new objects;
        dicts and lists are rebuilt recursively).
    '''
    if isinstance(d, dict):
        return {k: replace_in_dict(v, target, replacement) for k, v in d.items()}
    if isinstance(d, list):
        return [replace_in_dict(v, target, replacement) for v in d]
    if isinstance(d, str):
        return d.replace(target, replacement)
    return d
