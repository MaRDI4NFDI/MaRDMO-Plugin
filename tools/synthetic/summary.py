'''A readable summary of what an export writes, from its golden file (tests/data/golden).

For review: every item the export creates, with its statements as
"property: target", and the statements it adds to items of the MaRDI Portal.
Names come from MaRDMO's data files (properties and items) and the payload
itself; QIDs that are neither stay QIDs.

    python -m tools.synthetic.summary synthetic_model > synthetic_model.md
'''
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
GOLDEN = ROOT / 'tests' / 'data' / 'golden'
DATA = ROOT / 'MaRDMO' / 'data'


def names():
    properties = {pid: name for name, pid in json.loads((DATA / 'properties.json').read_text()).items()}
    items = {qid: name for name, qid in json.loads((DATA / 'items.json').read_text()).items()}
    return properties, items


def summary(name):
    data = json.loads((GOLDEN / f'{name}.json').read_text(encoding='utf-8'))
    payload = data['payload']
    properties, items = names()
    labels = {key: item.get('label', '') for key, item in payload.items() if key.startswith('Item')}
    labels.update({item['id']: item.get('label', '') for item in payload.values() if item.get('id')})

    def target(value):
        if isinstance(value, str):
            return labels.get(value) or items.get(value) or value
        return json.dumps(value, ensure_ascii=False)

    def qualifiers(entries):
        return ''.join(f' [{properties.get(q["property"]["id"], q["property"]["id"])}: '
                       f'{target(q["value"].get("content"))}]' for q in entries)

    lines = [f'# {name}', '', f'{len(data["messages"])} messages; {len(data["written"])} items in the write order.', '']
    new = [(key, item) for key, item in payload.items() if key.startswith('Item') and not item.get('id')]
    lines += [f'## New items ({len(new)})', '']
    for key, item in sorted(new, key=lambda pair: (pair[1].get('class', ''), pair[1].get('label', ''))):
        lines.append(f'### {item.get("label", "")} ({item.get("class", "")})')
        if item.get('description'):
            lines.append(f'*{item["description"]}*')
        lines.append('')
        for prop, _, value, *rest in item.get('statements', []):
            lines.append(f'- {properties.get(prop, prop)}: {target(value)}{qualifiers(rest[0] if rest else [])}')
        lines.append('')
    added = [entry for key, entry in payload.items() if key.startswith('RELATION')]
    lines += [f'## Statements on items of the MaRDI Portal ({len(added)})', '']
    for entry in added:
        subject = entry['url'].rsplit('/statements', 1)[0].rsplit('/', 1)[-1]
        statement = entry['payload']['statement']
        prop = statement['property']['id']
        lines.append(f'- {target(subject)} — {properties.get(prop, prop)}: '
                     f'{target(statement["value"].get("content"))}{qualifiers(statement.get("qualifiers", []))}')
    aliases = [entry for key, entry in payload.items() if key.startswith('ALIAS')]
    lines += ['', f'## Aliases added to items ({len(aliases)})', '']
    for entry in aliases:
        subject = entry['url'].rsplit('/aliases', 1)[0].rsplit('/', 1)[-1]
        lines.append(f'- {target(subject)}: {", ".join(entry["payload"]["aliases"])}')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    sys.stdout.write(summary(sys.argv[1]))
