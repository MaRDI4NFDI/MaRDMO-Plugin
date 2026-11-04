"""What the export of an unchanged import would write, from saved payloads, offline.

Plain Python, no Django and no portal:  python3 unchanged_export.py <results dir> ...
(results of preview_payload.py or roundtrip_collect.py; MARDMO, default
~/Work/MaRDMO-Plugin/MaRDMO, for the property names).

An item filled from the portal and exported without changes must write
nothing: every statement of the payload is on the portal already
(RELATION ... exists 'true') and no item is new.  Lists per item the
statements that would be written ('false') or extended ('partial', with
the qualifiers that would be added), and new items.  Exit status 1 if any.

items.json "multirole": models whose tasks or formulas hold statements with
several roles (e.g. "contains X as initial value of an ODE and parameter").
"""
import json, os, sys


CODE = os.path.expanduser(os.environ.get('MARDMO', '~/Work/MaRDMO-Plugin/MaRDMO'))


def load_properties(folder):
    """Property name -> ID: saved by preview_payload.py, else MaRDMO's data/properties.json."""
    path = os.path.join(folder, 'properties.json')
    if not os.path.exists(path):
        path = os.path.join(CODE, 'data', 'properties.json')
    return json.load(open(path))


def report(folder):
    pname = {v: k for k, v in load_properties(folder).items()}
    written = 0
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.json') or name == 'properties.json':
            continue
        result = json.load(open(os.path.join(folder, name)))
        payload = result.get('payload')
        if not payload:
            print(f"{name[:-5]}: no payload ({result.get('export message') or 'export crash'})")
            continue

        def ident(value):
            """Payload value -> QID, NEW:<label> for a new item, or the literal."""
            if isinstance(value, str) and value in payload:
                return payload[value].get('id') or f"NEW:{payload[value].get('label', '')}"
            return value

        relations = [e for k, e in payload.items() if k.startswith('RELATION')]
        changes = [e for e in relations if e.get('exists') != 'true']
        new_items = [e.get('label') for k, e in payload.items() if k.startswith('Item') and not e.get('id')]
        written += len(changes) + len(new_items)
        print(f"{name[:-5]}: {len(relations)} statements, {len(changes)} would be written, "
              f"{len(new_items)} new items {new_items or ''}")
        for e in changes:
            st = e['payload']['statement']
            quals = [(pname.get(q['property']['id'], q['property']['id']), ident(q['value']['content']))
                     for q in st.get('qualifiers', [])]
            line = (f"   {e.get('exists'):8} {ident(e['url'].split('/')[-2])} "
                    f"{pname.get(st['property']['id'], st['property']['id'])} {ident(st['value']['content'])} {quals}")
            if e.get('exists') == 'partial':
                line += f"  adds {[ident(q['value']['content']) for q in e.get('add_qualifiers', [])]}"
            print(line)
    return written


if __name__ == '__main__':
    total = sum(report(folder) for folder in sys.argv[1:])
    print('would be written in total:', total)
    sys.exit(1 if total else 0)
