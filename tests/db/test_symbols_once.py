'''A symbol is entered once; the formulas that use it get its row (#179).

Each documentation is exported with only the rows the rule needs — one row
per symbol that stands for one quantity, a row in every table for a symbol
that stands for several — and must export exactly as with all its rows (its
golden file of tests/db/test_export.py).  A symbol that stands for several
quantities and has no row in a formula that uses it prevents the export.
'''
import collections
import json
import re

import pytest
from rdmo.projects.models import Value

from MaRDMO.core.constants import BASE_URI
from MaRDMO.model.symbols import canonical
from tests.db.test_export import DATA, export, imported

DOCUMENTATIONS = ['chattopadhyay_1997', 'chowdhury_2020', 'mendez_2022', 'white_2006']
TABLES = [f'{BASE_URI}domain/{section}/element/' for section in ('quantity', 'formulation')]


def unordered(result):
    '''*result* without what does not matter to the portal: the order of statements and the numbers of new items.

    The payload numbers its new items in the order it meets them in the
    answers; with fewer rows a quantity is met later.  So every new item is
    named by its label, description and ID, a relation or an alias by its
    content, and every list is sorted.
    '''
    result = json.loads(json.dumps(result, default=str))
    payload = result.get('payload', {})
    names = {key: f"{entry.get('label')}|{entry.get('description')}|{entry.get('id')}"
             for key, entry in payload.items() if re.fullmatch(r'Item\d+', key)}
    text = re.sub(r'Item\d{10}', lambda match: names.get(match.group(), match.group()), json.dumps(result))
    result = json.loads(text)

    def sort(data):
        if isinstance(data, dict):
            return {key: sort(value) for key, value in data.items()}
        if isinstance(data, list):
            return sorted((sort(value) for value in data), key=lambda item: json.dumps(item, sort_keys=True))
        return data
    result['payload'] = {(key if not re.fullmatch(r'[A-Z]+\d+', key) else
                          re.sub(r'\d+', '', key) + json.dumps(sort(entry), sort_keys=True)): sort(entry)
                         for key, entry in result.get('payload', {}).items()}
    return sort(result)


def rows(documentation):
    '''``[(set prefix, set index, symbol, quantity ID, [values])]`` of every symbol table row, quantities first.'''
    found = collections.defaultdict(lambda: {'symbol': '', 'quantity': '', 'values': []})
    for value in Value.objects.filter(project=documentation, snapshot=None,
                                      attribute__uri__startswith=f'{BASE_URI}domain/').select_related('attribute'):
        table = next((table for table in TABLES if value.attribute.uri.startswith(table)), None)
        if table is None:
            continue
        row = found[(TABLES.index(table), value.set_prefix, value.set_index)]
        field = value.attribute.uri.rsplit('/', 1)[1]
        row[field] = value.external_id if field == 'quantity' else value.text
        row['values'].append(value.pk)
    return [(key, row) for key, row in sorted(found.items(), key=lambda item: (item[0][0], item[0][1].split('|'),
                                                                               item[0][2]))]


def keep_only_needed(documentation):
    '''Delete every row the rule does not need; return how many rows are left.'''
    table = rows(documentation)
    quantities = collections.defaultdict(set)
    for _, row in table:
        quantities[canonical(row['symbol'])].add(row['quantity'])
    seen, left = set(), 0
    for _, row in table:
        symbol = canonical(row['symbol'])
        if len(quantities[symbol]) == 1 and symbol in seen:
            Value.objects.filter(pk__in=row['values']).delete()
        else:
            left += 1
        seen.add(symbol)
    return left


@pytest.mark.parametrize('name, needed', [('chattopadhyay_1997', 17), ('chowdhury_2020', 59), ('mendez_2022', 33),
                                          ('white_2006', 12)])
def test_a_symbol_entered_once_exports_as_entered_everywhere(name, needed, project, portal):
    portal(f'export_{name}')
    documentation = imported(project, name)
    assert keep_only_needed(documentation) == needed
    golden = json.loads((DATA / 'golden' / f'{name}.json').read_text(encoding='utf-8'))
    assert unordered(export(documentation)) == unordered(golden)


def test_a_symbol_for_several_quantities_needs_its_row(project, portal):
    '''chowdhury_2020: "h" is the effective hormone level in one model, the blood insulin excess in the other.'''
    portal('export_chowdhury_2020')
    documentation = imported(project, 'chowdhury_2020')
    first = next(row for _, row in rows(documentation) if row['symbol'] == 'h')
    Value.objects.filter(pk__in=first['values']).delete()
    messages = export(documentation)['messages']
    assert any('Symbol "h" stands for different quantities in this documentation (cf. pages' in message
               for message in messages), messages
