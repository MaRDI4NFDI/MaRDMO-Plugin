'''Values of the payload the portal would reject, found before anything is posted.'''
import re

from django.utils.translation import gettext as _

from ..core.patterns import QUANTITY_AMOUNT_RE
from ..components.validators import (
    REPOSITORY_URL_SCHEMES,
    WEB_URL_SCHEMES,
    doi_problem,
    swmath_problem,
    url_problem,
)
from .bodies import ITEM_KEY_RE

TIME_RE = re.compile(r'^\+?(-?\d+)-(\d{2})-(\d{2})(T.*)$')


def invalid_values(dictionary, properties):
    '''Malformed URLs, DOIs, swMATH IDs, dates and amounts of the payload *dictionary*, one message each.

    Applies the strict rules from :mod:`~MaRDMO.components.validators` to every URL
    statement and qualifier and to every "DOI" and "swMath work ID" value,
    checks that every time value is a ``+YYYY-MM-DDThh:mm:ssZ`` string and
    every quantity amount a Wikibase decimal (``+8``, ``+1.5``).  Only what
    is written: RELATION entries the portal has already are left out (#167).

    Args:
        dictionary: The payload dictionary.
        properties: ``{name: PID}`` of the portal.
    '''
    pid_to_name = {pid: name for name, pid in properties.items()}
    repository_pid = properties.get('source code repository URL')
    doi_pid = properties.get('DOI')
    swmath_pid = properties.get('swMath work ID')
    errors = []

    def check(item_name, prop_id, data_type, value):
        if data_type == 'quantity':
            text = str(value.get('amount', '')) if isinstance(value, dict) else str(value)
            if not QUANTITY_AMOUNT_RE.match(text):
                errors.append(_('"{item}", {property}: invalid number ("{value}")').format(
                    item=item_name, property=pid_to_name.get(prop_id, prop_id), value=text.lstrip('+')))
            return
        if data_type == 'time':
            text = value.get('time', '') if isinstance(value, dict) else str(value)
            if not TIME_RE.match(text):
                errors.append(_('"{item}", {property}: invalid date ("{value}")').format(
                    item=item_name, property=pid_to_name.get(prop_id, prop_id), value=text))
            return
        text = value if isinstance(value, str) else ''
        if not text:
            return
        if prop_id == doi_pid:
            problem = doi_problem(text)
        elif prop_id == swmath_pid:
            problem = swmath_problem(text)
        else:
            schemes = REPOSITORY_URL_SCHEMES if prop_id == repository_pid else WEB_URL_SCHEMES
            problem = url_problem(text, schemes)
        if problem:
            shown = text if len(text) <= 60 else f'{text[:57]}...'
            errors.append(f'"{item_name}", {pid_to_name.get(prop_id, prop_id)}: {problem} ("{shown}")')

    def relevant(prop_id, data_type):
        return data_type in ('url', 'URL', 'time', 'quantity') or prop_id in (doi_pid, swmath_pid)

    def check_statement(item_name, prop_id, data_type, value, qualifiers):
        if relevant(prop_id, data_type):
            check(item_name, prop_id, data_type, value)
        for qualifier in qualifiers or []:
            q_type = qualifier['property']['data_type']
            if relevant(qualifier['property']['id'], q_type):
                check(item_name, qualifier['property']['id'], q_type, qualifier['value']['content'])

    for key, entry in dictionary.items():
        if key.startswith('Item'):
            for statement in entry.get('statements', []):
                check_statement(
                    entry.get('label') or key, statement[0], statement[1], statement[2],
                    statement[3] if len(statement) > 3 else [],
                )
        elif key.startswith('RELATION'):
            # Only what is written: not a statement the portal has, of one it
            # extends only the qualifiers it adds (#167)
            if entry.get('exists') == 'true':
                continue
            item_key = entry['url'].split('/items/')[1].split('/')[0]
            item_name = dictionary.get(item_key, {}).get('label') or item_key
            statement = entry['payload']['statement']
            if entry.get('exists') == 'partial':
                for qualifier in entry.get('add_qualifiers', []):
                    if relevant(qualifier['property']['id'], qualifier['property']['data_type']):
                        check(item_name, qualifier['property']['id'], qualifier['property']['data_type'],
                              qualifier['value']['content'])
                continue
            check_statement(
                item_name, statement['property']['id'], statement['property']['data_type'],
                statement['value']['content'], statement.get('qualifiers', []),
            )
    return errors


def dangling_references(dictionary):
    '''Messages for ``Item<n>`` placeholders of the payload *dictionary* that refer to no item of the export.

    Every placeholder is replaced by the QID of its item while posting; one
    without an item would reach the portal as a value it rejects, after
    other items may have been created already.
    '''
    found = []

    def walk(value, owner):
        if isinstance(value, dict):
            for inner in value.values():
                walk(inner, owner)
        elif isinstance(value, (list, tuple)):
            for inner in value:
                walk(inner, owner)
        elif isinstance(value, str) and ITEM_KEY_RE.match(value) and value not in dictionary:
            found.append(_('"{owner}": refers to an item that is not part of the export ({key}); '
                           'nothing was exported, please report this to the MaRDMO developers').format(
                               owner=owner, key=value))

    for key, entry in dictionary.items():
        if key.startswith('Item'):
            walk(entry.get('statements', []), entry.get('label') or key)
        else:
            # RELATION and ALIAS entries: the subject in the URL and the payload
            item_key = entry.get('url', '').split('/items/')[-1].split('/')[0]
            owner = dictionary.get(item_key, {}).get('label') or item_key
            walk([item_key, entry.get('payload', {})], owner)
    return list(dict.fromkeys(found))
