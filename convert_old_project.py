'''One-off: convert a project export of MaRDMO before 0.8.0 to item IDs (test data only).

Pages and items entered without page get deterministic user: IDs; a relation
gets the ID of the page of its item, found once by name and description in
the sections its dropdown offers.  Own items entered without page
(programming languages, CPU models, methods, instruments, and in the
workflow catalog research fields and algorithmic tasks) keep only their
label as text (#129): MaRDMO adds a generic description.  Texts of portal
and Wikidata items lose their source tag (#103).  New authors and journals
of publications get their user: ID instead of "no author found" / "no
journal found" (#118, the same as MaRDMO.ids.part_id).  Only <external_id> and
those <text> lines change; projects converted before are converted again.

    cd ~/Work/MaRDMO-Plugin
    PYTHONPATH=. python dev-tests/convert_old_project.py ~/Work/MaRDMO-Questionnaire/catalog <project.xml>...
'''
import html
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path.home() / 'Work/MaRDMO-Plugin'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
import django  # noqa: E402
django.setup()
from MaRDMO.helpers import extract_parts  # noqa: E402
from MaRDMO.ids import part_id  # noqa: E402
from MaRDMO.optionsets import PROVIDERS  # noqa: E402

DOMAIN = 'https://rdmo.mardi4nfdi.de/terms/domain/'
DC = '{http://purl.org/dc/elements/1.1/}uri'
PAGES = ['algorithm', 'benchmark', 'dataset', 'field', 'formulation', 'hardware', 'model',
         'problem', 'processstep', 'publication', 'quantity', 'software', 'task', 'workflow']
VALUE = re.compile(r'<value>.*?</value>', re.S)
# Answers whose own items have no page (#129)
WITHOUT_PAGE = {'software/programming-language-relatant', 'hardware/cpu', 'processstep/method-relatant',
                'processstep/instrument-relatant', 'processstep/field-relatant', 'algorithm/problem-relatant'}


def field(block, name):
    match = re.search(rf'<{name}>(.*?)</{name}>', block, re.S)
    return html.unescape(match.group(1)) if match else ''


def attribute(block):
    return re.search(r'<attribute dc:uri="([^"]*)"', block).group(1)


def sections_of(catalog):
    '''{attribute path: sections of own items its dropdown offers} from the questionnaire.'''
    keys = {e.get(DC): e.findtext('provider_key') for e in ET.parse(catalog / 'optionsets.xml').getroot()}
    result = {}
    for path in catalog.glob('*-catalog.xml'):
        for question in ET.parse(path).getroot().iter('question'):
            node = question.find('attribute')
            if node is None or not node.get(DC):
                continue
            for optionset in question.iter('optionset'):
                key = keys.get(optionset.get(DC))
                if key:
                    result[node.get(DC)[len(DOMAIN):]] = PROVIDERS[key].answers or []
    return result


def convert(path, sections):
    text = path.read_text(encoding='utf-8')
    blocks = VALUE.findall(text)
    values = [(attribute(b)[len(DOMAIN):] if attribute(b).startswith(DOMAIN) else attribute(b), b) for b in blocks]

    # Pages: their ID, name and description
    by_attr = defaultdict(dict)
    for attr, block in values:
        by_attr[attr][(field(block, 'set_prefix'), field(block, 'set_index'))] = block
    page_ids, pages = {}, defaultdict(list)
    for section in PAGES:
        for (prefix, index), block in by_attr.get(f'{section}/id', {}).items():
            if field(block, 'external_id') != 'not found':
                continue
            sibling = ('', index) if section == 'publication' else (index, '0')
            name = field(by_attr.get(f'{section}/name', {}).get(sibling, ''), 'text')
            description = field(by_attr.get(f'{section}/description', {}).get(sibling, ''), 'text')
            user_id = f'user:{uuid.uuid5(uuid.NAMESPACE_URL, f"mardmo-test/{path.stem}/{section}/{index}")}'
            page_ids[block] = user_id
            pages[section].append((name, description, user_id))

    new, report = {}, Counter()
    for attr, block in values:
        if field(block, 'external_id') != 'not found':
            continue
        if block in page_ids:
            new[block] = page_ids[block]
            report['page'] += 1
            continue
        label, description, _ = extract_parts(field(block, 'text'))
        found = [user_id for section in sections.get(attr, []) for name, desc, user_id in pages[section]
                 if (name, desc) == (label, description)]
        if len(found) == 1:
            new[block] = found[0]
            report['relation to page'] += 1
        elif not found:
            key = f'mardmo-test/{path.stem}/{attr}/{field(block, "set_prefix")}/{field(block, "set_index")}/' \
                  f'{field(block, "collection_index")}'
            new[block] = f'user:{uuid.uuid5(uuid.NAMESPACE_URL, key)}'
            report['without page' if not sections.get(attr) else 'NO PAGE FOUND'] += 1
            if sections.get(attr):
                print(f'  {path.name}: no page in {sections[attr]} for {attr}: {field(block, "text")!r}')
        else:
            print(f'  {path.name}: {len(found)} pages for {attr}: {field(block, "text")!r}')
            report['AMBIGUOUS'] += 1

    changes = {}
    for block, user_id in new.items():
        changes[block] = block.replace('<external_id>not found</external_id>', f'<external_id>{user_id}</external_id>')

    # Own items without page: the label only (#129)
    ids_of_pages = {field(b, 'external_id') for a, b in values if a in {f'{s}/id' for s in PAGES}} | set(page_ids.values())
    for attr, block in values:
        identifier = new.get(block) or field(block, 'external_id')
        if attr not in WITHOUT_PAGE or not identifier.startswith('user:') or identifier in ids_of_pages:
            continue
        typed = field(block, 'text')
        label = extract_parts(typed)[0]
        if label != typed:
            changes[block] = changes.get(block, block).replace(f'<text>{escape(typed)}</text>', f'<text>{escape(label)}</text>')
            assert changes[block] != block or block in new, (path.name, typed)
            print(f'  {path.name}: {attr}: {typed!r} -> {label!r}')
            report['label only'] += 1

    # Portal and Wikidata items: no source tag in the text (#103)
    for attr, block in values:
        identifier = field(block, 'external_id')
        typed = field(block, 'text')
        for source in ('mardi', 'wikidata'):
            if identifier.startswith(f'{source}:') and typed.endswith(f' [{source}]'):
                untagged = typed[:-len(f' [{source}]')]
                changes[block] = changes.get(block, block).replace(
                    f'<text>{escape(typed)}</text>', f'<text>{escape(untagged)}</text>')
                report['tag removed'] += 1

    # New authors and journals of publications (#118): the ID is the text
    part_fields = {'author': ('orcid', 'zbmath', 'wikidata', 'name'), 'journal': ('issn', 'name')}
    for attr, block in values:
        for kind, keys in part_fields.items():
            if attr != f'publication/{kind}/id' or field(block, 'text') != f'no {kind} found':
                continue
            index = (field(block, 'set_index'), field(block, 'collection_index'))
            sibling = {key: field(next((b for a, b in values if a == f'publication/{kind}/{key}'
                                        and (field(b, 'set_index'), field(b, 'collection_index')) == index), ''), 'text')
                       for key in keys}
            user_id = part_id(kind, *(sibling[key] for key in keys))
            changes[block] = changes.get(block, block).replace(f'<text>no {kind} found</text>', f'<text>{user_id}</text>')
            report[f'new {kind}'] += 1

    for block, changed in changes.items():
        assert text.count(block) == 1
        text = text.replace(block, changed)
    path.write_text(text, encoding='utf-8')
    print(path.name, dict(report), '| left:', text.count('<external_id>not found</external_id>'))


if __name__ == '__main__':
    catalog = Path(sys.argv[1])
    sections = sections_of(catalog)
    for name in sys.argv[2:]:
        convert(Path(name), sections)
