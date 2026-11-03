"""Compare the saved previews with the saved payloads (from preview_payload.py), offline.

Plain Python, no Django and no portal:  python3 preview_compare.py <results dir> ...

The preview is parsed into items (page code, name, portal ID) and relations
(page code, relation label, target, assumptions), plus formulas, formula
elements, aliases and the text of each item.  Items and statements of the
payload are matched against it in both directions:

- every item of the preview is in the payload, every new item of the
  payload is in the preview
- every relation of the preview is a statement of the payload between the
  two items (either direction, or as qualifier), every statement between two
  items of the payload is shown in the preview (as relation, assumption or
  formula element)
- formulas, formula elements and aliases agree; every other literal of the
  payload (descriptions, IDs, URLs, ...) occurs in the preview text of its item

Statements MaRDMO adds to every item (instance of, MaRDI profile type,
community) are not shown in the preview and not compared.
"""
import collections, glob, html, json, os, re, sys

STANDARD = {'instance of', 'MaRDI profile type', 'community'}
# relation label in the preview -> (property, direction, role) in the payload; '->' from the item
# of the page to the target, '<-' the other way, 'any' either way; the role is the value of the
# qualifier "object has role".  Keys are (relation block, label) or just the label.
_ROLE = {'analytical solution': 'Q6775641', 'boundary condition': 'Q6534259', 'constant': 'Q6480317',
         'constraint condition': 'Q6534262', 'governing equation': 'Q7270342', 'initial condition': 'Q6534264',
         'input': 'Q6480299', 'output': 'Q6480295', 'parameter': 'Q6480341'}
_SOURCE_ROLE = {'analyzes': 'Q6825292', 'documents': 'Q6672349', 'invents': 'Q6672344', 'surveys': 'Q6672366',
                'uses': 'Q6480405'}
RELATION_TYPES = {
    'specialized by': ('specialized by', '->', None), 'specializes': ('specialized by', '<-', None),
    'linearized by': ('linearized by', '->', None), 'linearizes': ('linearized by', '<-', None),
    'discretized by': ('discretized by', '->', None), 'discretizes': ('discretized by', '<-', None),
    'nondimensionalized by': ('nondimensionalized by', '->', None),
    'nondimensionalizes': ('nondimensionalized by', '<-', None),
    'approximated by': ('approximated by', '->', None), 'approximates': ('approximated by', '<-', None),
    'similar to': ('similar to', 'any', None), 'assumes': ('assumes', '->', None),
    'contains': ('contains', '->', None), 'contained in': ('contains', '<-', None),
    'contained in Field': ('contains', '<-', None), 'models': ('modelled by', '<-', None),
    'used by': ('used by', '->', None), 'field of work': ('field of work', '->', None),
    'input data set': ('input data set', '->', None), 'output data set': ('output data set', '->', None),
    'subclass of': ('subclass of', '->', None), 'has subclass': ('subclass of', '<-', None),
    'solves': ('solved by', '<-', None), 'implemented by': ('implemented by', '->', None),
    'instantiated by': ('manifestation of', '<-', None), 'programmed in': ('programmed in', '->', None),
    'depends on software': ('depends on software', '->', None), 'tests': ('tested by', '<-', None),
    'CPU': ('CPU', '->', None),
    'author': ('author', '->', None), 'published in': ('published in', '->', None),
    'language of work or name': ('language of work or name', '->', None),
    **{f'contains {role}': ('contains', '->', qid) for role, qid in _ROLE.items()},
    **{('P2E', label): ('described by source', '<-', qid) for label, qid in _SOURCE_ROLE.items()},
    **{('P2A', label): ('described by source', '<-', qid) for label, qid in _SOURCE_ROLE.items()},
    **{('P2BS', label): ('described by source', '<-', qid) for label, qid in _SOURCE_ROLE.items()},
    **{('P2HS', label): ('described by source', '<-', qid) for label, qid in _SOURCE_ROLE.items()},
}
# shown as qualifiers or pairs, only the link between the two items is compared
QUALIFIER_LABELS = {'uses', 'Software-Environment', 'Hardware-Environment', 'Instrument-Environment', 'relevant'}

# statements to fixed portal items that the preview shows as an answer: (property, item) -> preview text
SHOWN_AS_ANSWER = {
    ('mandates', 'Q6480291'): 'Data Set Publication: Yes',         # data publishing
    ('mandates', 'Q6480370'): 'Data Set Archiving: Yes',           # research data archiving
}
CODE = re.compile(r'^[A-Z]+\d+$')
QID = re.compile(r'^(mardi|wikidata):(Q\d+)$')


def text(fragment):
    """Visible text of an HTML fragment, whitespace collapsed."""
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', fragment))).strip()


def parse_preview(page):
    """Return {code: item} with name, section, ID, relations, formulas, elements, aliases, text."""
    # collapse whitespace outside the TeX of formulas, which is compared exactly
    tex = []
    page = re.sub(r'data-tex="([^"]*)"', lambda m: tex.append(html.unescape(m.group(1))) or f'data-tex="{len(tex) - 1}"', page)
    page = re.sub(r'\s+', ' ', page)

    def formulas_in(fragment):
        return [tex[int(t)] for t in re.findall(r'data-tex="(\d+)"', fragment)]

    items, item, section = {}, None, None
    heads = list(re.finditer(r'<h([123])(?: id="([^"]*)")?>(.*?)</h\1>', page))
    for n, head in enumerate(heads):
        level, anchor = head.group(1), head.group(2) or text(head.group(3))
        body = page[head.end():heads[n + 1].start() if n + 1 < len(heads) else len(page)]
        if level == '1':
            section, item = anchor, None
            continue
        if level == '2':
            name = text(head.group(3)).split(': ', 1)[1] if ': ' in text(head.group(3)) else ''
            item = items[anchor] = {'code': anchor, 'section': section, 'name': name, 'id': None,
                                    'relations': [], 'formulas': [], 'elements': [], 'aliases': [], 'text': ''}
            found = re.search(r'<b>(MaRDI Portal|Wikidata) ID</b>: (Q\d+)', body)
            if found:
                item['id'] = ('mardi:' if found.group(1) == 'MaRDI Portal' else 'wikidata:') + found.group(2)
        if item is None:
            continue
        # formulas, formula elements and aliases, also in the sub-blocks (quantity definitions)
        formulas = re.search(r'<b>Defining formulations</b>:(.*?)</ol>', body)
        if formulas:
            item['formulas'] += formulas_in(formulas.group(1))
        for row in re.findall(r'<tr>(.*?)</tr>', body):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row)
            if len(cells) == 6:
                symbol = formulas_in(cells[0])
                quantity = text(cells[2]) or text(cells[4])   # quantity or quantity kind
                name_cell = text(cells[1]) or text(cells[3])
                item['elements'].append((symbol[0] if symbol else text(cells[0]),
                                         quantity if quantity != '-' else name_cell))
        aliases = re.search(r'<b>Alias</b>:(.*?)</ol>', body)
        if aliases:
            item['aliases'] += [text(a) for a in re.findall(r'<li[^>]*>(.*?)</li>', aliases.group(1))]
        # publication: authors, journal and language in the collapsed details
        details = re.search(r'<details class="mardmo-details">(.*?)</details>', body)
        for entry in re.findall(r'<li>(.*?)</li>', details.group(1)) if details else []:
            entry = text(entry)
            if entry.startswith('Journal: '):
                links = [('published in', entry[len('Journal: '):].split(' — ')[0])]
            elif entry.startswith('Language: '):
                links = [('language of work or name', name) for name in entry[len('Language: '):].split(', ')]
            else:
                name, status = entry.split(' — ', 1)
                # authors without any identifier are only a name ("author name string")
                links = [] if status.startswith('name only') else [('author', name)]
            # a publication already on the portal gets nothing added: its details are information only
            block = 'publication on portal' if 'nothing is added to it' in body else 'publication details'
            item['relations'] += [{'block': block, 'label': label, 'target': target,
                                   'assumptions': []} for label, target in links]
        item['text'] += ' ' + text(body) + ' ' + ' '.join(formulas_in(body))
        if level == '3' and text(head.group(3)).startswith('Relevant Mathematical Models'):
            # workflow: models and their tasks, listed by name
            for name in re.findall(r'<li[^>]*>([^<]*)', body):
                name = text(name).lstrip('→ ').strip()
                if name and 'MISSING' not in name:
                    item['relations'].append({'block': anchor, 'label': 'relevant', 'target': name, 'assumptions': []})
        elif level == '3':
            for line in re.split(r'<br>|</li>|<li[^>]*>', body):
                line = text(line)
                assumptions = []
                if ' - assumptions (general to special):' in line:
                    line, rest = line.split(' - assumptions (general to special):', 1)
                    assumptions = [a.strip() for a in rest.split(',')
                                   if a.strip() and 'MISSING' not in a and 'NOT FOUND' not in a]
                line = re.sub(r'^(→|->|\d+\.)\s*', '', line.strip()).strip()
                if ': ' not in line or 'MISSING' in line or 'NOT FOUND' in line:
                    continue
                label, target = line.split(': ', 1)
                # an item: page code, portal ID or "Name (Description)"; anything else is a literal
                if len(label) > 40 or not (CODE.match(target.strip()) or QID.match(target.strip()) or ' (' in target):
                    continue
                item['relations'].append({'block': anchor, 'label': label, 'target': target.strip(),
                                          'assumptions': assumptions})
    return items


def parse_payload(payload):
    """Return items {key: ...} and statements [(subject, property, type, value, qualifiers, exists)]."""
    items, statements, aliases = {}, [], collections.defaultdict(list)
    for key, entry in payload.items():
        if key.startswith('Item'):
            items[key] = entry
            for st in entry.get('statements') or []:
                quals = [(q['property']['id'], q['value']['content']) for q in (st[3] if len(st) > 3 else [])
                         if isinstance(q, dict)]
                statements.append((key, st[0], st[1], st[2], quals, None))
            aliases[key] += ((entry.get('payload') or {}).get('item', {}).get('aliases') or {}).get('en', [])
    for key, entry in payload.items():
        if key.startswith('RELATION'):
            subject = entry['url'].split('/items/')[1].split('/')[0]
            st = entry['payload']['statement']
            quals = [(q['property']['id'], q['value'].get('content')) for q in st.get('qualifiers') or []]
            statements.append((subject, st['property']['id'], st['property']['data_type'],
                               st['value'].get('content'), quals, entry.get('exists')))
        elif key.startswith('ALIAS'):
            aliases[entry['url'].split('/items/')[1].split('/')[0]] += entry['payload']['aliases']
    return items, statements, aliases


def compare(page, payload, props):
    pname = {v: k for k, v in props.items()}
    preview = parse_preview(page)
    items, statements, aliases = parse_payload(payload)
    wikidata = {st[3]: st[0] for st in statements if st[1] == props.get('Wikidata QID')}

    # one node per item: the payload key, or the QID for items not in the payload
    by_qid = {e['id']: k for k, e in items.items() if e.get('id')}
    by_label = collections.defaultdict(list)
    for k, e in items.items():
        by_label[(e.get('label') or '').lower()].append(k)

    def node_of_id(ident):
        source, qid = QID.match(ident).groups()
        if source == 'mardi':
            return by_qid.get(qid, qid)
        return wikidata.get(qid, 'wikidata:' + qid)

    def node_of_item(it):
        if it['id']:
            return node_of_id(it['id'])
        keys = by_label.get(it['name'].lower(), [])
        return keys[0] if len(keys) == 1 else None

    def node_of_target(target):
        if CODE.match(target) and target in preview:
            return node_of_item(preview[target])
        if QID.match(target):
            return node_of_id(target)
        label = re.sub(r' \(.*$', '', target).lower()    # user entity "Name (Description)"
        keys = by_label.get(label, [])
        return keys[0] if len(keys) == 1 else None

    def node_of_value(value):
        if isinstance(value, dict):      # quantities, times: not an item
            return json.dumps(value, sort_keys=True)
        return by_qid.get(value, value) if isinstance(value, str) and re.match(r'^Q\d+$', value) else value

    def shown_value(value):
        """A literal as the preview shows it: quantities by amount, times by year."""
        if isinstance(value, dict) and 'amount' in value:
            return value['amount'].lstrip('+')
        if isinstance(value, dict) and 'time' in value:
            return value['time'].lstrip('+')[:4]
        if isinstance(value, dict) and 'text' in value:      # monolingual text (title)
            return value['text']
        return value

    def contains(page_text, value, case=True):
        """Whether the preview text shows the literal (DOIs: in any case)."""
        value = re.sub(r'\s+', ' ', str(value)).strip()
        return value in page_text if case else value.lower() in page_text.lower()

    report = collections.defaultdict(list)
    nodes = {}
    for code, it in preview.items():
        nodes[code] = node_of_item(it)
        if nodes[code] is None:
            report['preview item not in payload'].append(f"{code} {it['name']}")
    node_code = {n: c for c, n in nodes.items() if n}

    # statements by unordered pair, qualifiers by subject
    pairs = collections.defaultdict(list)
    for s, p, dt, v, quals, _ in statements:
        if dt == 'wikibase-item':
            pairs[frozenset((s, node_of_value(v)))].append(pname.get(p, p))
        for qp, qv in quals:
            pairs[frozenset((s, node_of_value(qv)))].append(f'{pname.get(p, p)} / {pname.get(qp, qp)}')
            pairs[frozenset((node_of_value(v), node_of_value(qv)))].append(f'{pname.get(p, p)} / {pname.get(qp, qp)}')

    # preview -> payload
    shown = set()
    for code, it in preview.items():
        s = nodes[code]
        for rel in it['relations']:
            t = node_of_target(rel['target'])
            if s is None or t is None:
                report['preview relation with unknown target'].append(f"{code} {rel['label']}: {rel['target']}")
                continue
            shown.add(frozenset((s, t)))
            if rel['block'] == 'publication on portal':
                continue
            if not pairs.get(frozenset((s, t))):
                report['preview relation not in payload'].append(f"{code} {rel['label']}: {rel['target']}")
                continue
            expected = RELATION_TYPES.get((rel['block'], rel['label'])) or RELATION_TYPES.get(rel['label'])
            if expected is None:
                if not (rel['label'] in QUALIFIER_LABELS and rel['block'] not in ('P2E', 'P2A', 'P2BS', 'P2HS')):
                    report['preview relation label without expected property'].append(
                        f"{code} [{rel['block']}] {rel['label']}: {rel['target']} (payload: {pairs[frozenset((s, t))]})")
                continue
            prop, direction, role = expected
            if not any(pname.get(p) == prop and isinstance(v, str)
                       and ((direction in ('->', 'any') and a == s and node_of_value(v) == t)
                            or (direction in ('<-', 'any') and a == t and node_of_value(v) == s))
                       and (role is None or (props.get('object has role'), role) in q)
                       for a, p, dt, v, q, _ in statements):
                report['preview relation with other type in payload'].append(
                    f"{code} {rel['label']}: {rel['target']} (expected {prop} {direction}{' ' + role if role else ''}, "
                    f"payload: {pairs[frozenset((s, t))]})")
            for a in rel['assumptions']:
                n = node_of_target(a)
                shown.update({frozenset((s, n)), frozenset((t, n))})
                if not (pairs.get(frozenset((s, n))) or pairs.get(frozenset((t, n)))):
                    report['preview assumption not in payload'].append(f"{code} {rel['label']}: {rel['target']} assumes {a}")
        for symbol, quantity in it['elements']:
            q = node_of_target(quantity) if quantity else None
            if q:
                shown.add(frozenset((s, q)))

    # payload -> preview
    for s, p, dt, v, quals, exists in statements:
        label = pname.get(p, p)
        for qp, qv in quals:
            if isinstance(qv, str) and re.match(r'^(Item\d+|Q\d+)$', qv):
                continue           # items: compared as links between items
            if node_code.get(s) and re.sub(r'\s+', ' ', str(shown_value(qv))).strip() not in preview[node_code[s]]['text']:
                report['payload qualifier not in preview'].append(
                    f"{node_code[s]} {label} / {pname.get(qp, qp)}: {str(shown_value(qv))[:60]}")
        if label in STANDARD:
            continue
        where = node_code.get(s)
        if dt == 'wikibase-item':
            t = node_of_value(v)
            if frozenset((s, t)) not in shown:
                if (label, t) in SHOWN_AS_ANSWER and SHOWN_AS_ANSWER[(label, t)] in (preview[where]['text'] if where else ''):
                    continue
                if re.match(r'^Q\d+$', str(t)):
                    # a fixed item (data publishing, text data, ...): shown as an answer, listed for review
                    report['review: payload statement to a fixed item'].append(f"{where or s} {label} {t}")
                else:
                    report['payload statement not in preview'].append(
                        f"{where or s} {label} {node_code.get(t) or t} (exists: {exists})")
            continue
        v = shown_value(v)
        if where is None:
            # an item without a page (e.g. a CPU): its literals are shown where it is referenced
            texts = [it['text'] for c, it in preview.items()
                     if any(node_of_target(r['target']) == s for r in it['relations'])]
            if not any(re.sub(r'\s+', ' ', str(v)).strip() in t for t in texts):
                report['payload literal on item not in preview'].append(f"{s} {label}: {str(v)[:60]}")
            continue
        it = preview[where]
        if label == 'in defining formula':
            quantity = next((node_of_value(qv) for qp, qv in quals if pname.get(qp) == 'symbol represents'), None)
            if not any(sym == v and node_of_target(q) == quantity for sym, q in it['elements']):
                report['payload formula element not in preview'].append(f"{where} {v} -> {node_code.get(quantity) or quantity}")
        elif label == 'defining formula':
            if v not in it['formulas']:
                report['payload formula not in preview'].append(f"{where} {str(v)[:60]}")
        elif not contains(it['text'], v, case=label != 'DOI'):
            report['payload literal not in preview'].append(f"{where} {label}: {str(v)[:60]}")

    # formulas, elements and aliases of the preview -> payload
    for code, it in preview.items():
        s = nodes[code]
        if s is None:
            continue
        mine = [st for st in statements if st[0] == s]
        for f in it['formulas']:
            if not any(pname.get(st[1]) == 'defining formula' and st[3] == f for st in mine):
                report['preview formula not in payload'].append(f'{code} {f[:60]}')
        for symbol, quantity in it['elements']:
            q = node_of_target(quantity) if quantity else None
            if not any(pname.get(st[1]) == 'in defining formula' and st[3] == symbol
                       and any(node_of_value(qv) == q for qp, qv in st[4]) for st in mine):
                report['preview formula element not in payload'].append(f'{code} {symbol} -> {quantity}')
        if sorted(it['aliases']) != sorted(set(aliases.get(s, []))) and (it['aliases'] or aliases.get(s)):
            report['aliases differ'].append(f"{code}: preview {it['aliases']} payload {aliases.get(s, [])}")

    # new items of the payload must be in the preview
    for k, e in items.items():
        if not e.get('id') and k not in node_code:
            if not any(node_of_target(r['target']) == k for it in preview.values() for r in it['relations']) \
                    and not any(node_of_target(q) == k for it in preview.values() for _, q in it['elements']):
                report['new payload item not in preview'].append(f"{k} {e.get('class')} {e.get('label')}")
    counts = {'preview items': len(preview), 'preview relations': sum(len(i['relations']) for i in preview.values()),
              'payload items': len(items), 'payload statements': len(statements)}
    return counts, dict(report)


if __name__ == '__main__':
    total = collections.Counter()
    for folder in sys.argv[1:]:
        props = json.load(open(os.path.join(folder, 'properties.json')))
        for path in sorted(glob.glob(os.path.join(folder, '*.json'))):
            if path.endswith('properties.json'):
                continue
            res = json.load(open(path))
            if 'payload' not in res:
                print(f"{res['qid']:11} no payload: {(res.get('export message') or [res.get('error', '')[-200:]])[0][:120]}")
                continue
            counts, report = compare(open(path[:-5] + '.html').read(), res['payload'], props)
            total.update({k: len(v) for k, v in report.items()})
            print(f"{res['qid']:11} {counts}  {'ok' if not report else ''}")
            for kind, entries in report.items():
                print(f'    {kind} ({len(entries)}): {entries[:4]}')
    print('\ntotal:', dict(total) or 'no differences')
