"""Static check: attribute and option URIs used by MaRDMO against the questionnaire XML.

No network, no database.  Run from anywhere:

    python3 dev-tests/static_attributes.py

QUESTIONNAIRE points to the catalog folder of the questionnaire repo
(default ~/Work/MaRDMO-Questionnaire/catalog).

Errors (exit code 1):
  - an attribute used by the code is not defined in attributes.xml
  - an option used by the code is not defined in optionsets.xml
Warnings:
  - an attribute used by the code is defined, but no catalog question or
    question set uses it (MaRDMO writes or reads values nobody sees)
Info:
  - catalog attributes the code never names (entered by hand only)
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / 'MaRDMO'
QUESTIONNAIRE = Path(os.environ.get('QUESTIONNAIRE', '~/Work/MaRDMO-Questionnaire/catalog')).expanduser()
BASE = 'https://rdmo.mardi4nfdi.de/terms/'
DC = '{http://purl.org/dc/elements/1.1/}uri'
OPTIONS = BASE + 'options/'

# Background data of a publication: filled by the citation lookup, not shown
# in any catalog (see publication.utils.clean_background_data)
KNOWN_HIDDEN = {
    'domain/search',
    *(f'domain/publication/{a}' for a in (
        'name', 'description', 'title', 'date', 'volume', 'issue', 'page', 'entry-type',
        'author/id', 'author/name', 'author/description', 'author/orcid', 'author/wikidata', 'author/zbmath',
        'journal/id', 'journal/name', 'journal/description', 'journal/issn',
        'language/id', 'language/name', 'language/description')),
}
# mapping.json URLs of static relations: written without an RDMO option
# (add_relations_static), the URL is only a key of the export mapping
KNOWN_INTERNAL = {OPTIONS + o for o in (
    'mathmodb/contained-in', 'mathmoddb/models', 'mathmoddb/used-by',
    'mathalgodb/solves', 'mathalgodb/implemented-by', 'mathalgodb/instantiates', 'mathalgodb/tested-by')}


def code_attributes():
    '''Return {attribute path: [where]} for every attribute the code names.'''
    found = {}
    for path in sorted(PACKAGE.rglob('questions.json')):
        def walk(node, trail):
            if isinstance(node, dict):
                uri = node.get('uri')
                if isinstance(uri, str) and uri.startswith('domain/'):
                    found.setdefault(uri, []).append(f'{path.relative_to(REPO)}: {" > ".join(trail)}')
                for key, value in node.items():
                    walk(value, trail + [key])
        walk(json.loads(path.read_text()), [])
    literal = re.compile(r'''['"/](domain/[a-z0-9][a-z0-9/_-]*[a-z0-9])['"]''')
    for path in sorted(PACKAGE.rglob('*.py')):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for match in literal.finditer(line):
                found.setdefault(match.group(1), []).append(f'{path.relative_to(REPO)}:{lineno}')
    return found


def options_json_usage():
    '''Return (used, unused) keys of data/options.json, by ``options[...]`` in the code.'''
    keys = json.loads((PACKAGE / 'data' / 'options.json').read_text())
    pattern = re.compile(r'''options(?:\(\))?\[['"]([^'"]+)['"]\]''')
    used = {m.group(1) for path in PACKAGE.rglob('*.py') for m in pattern.finditer(path.read_text())}
    return {k: v for k, v in keys.items() if k in used}, {k: v for k, v in keys.items() if k not in used}


def code_options():
    '''Return {option URI: [where]} for every option the code names.

    Entries of data/options.json the code never reads are left out (see
    :func:`options_json_usage`).
    '''
    found = {}
    _, unused = options_json_usage()
    for path in sorted(PACKAGE.rglob('*.json')):
        text = path.read_text()
        if path == PACKAGE / 'data' / 'options.json':
            text = '\n'.join(f'"{v}"' for k, v in json.loads(text).items() if k not in unused)
        for match in re.finditer(r'"(https://rdmo\.mardi4nfdi\.de/terms/options/[^"]+)"', text):
            found.setdefault(match.group(1), []).append(str(path.relative_to(REPO)))
    for path in sorted(PACKAGE.rglob('*.py')):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for match in re.finditer(r'''(https://rdmo\.mardi4nfdi\.de/terms/options/[^'"\s]+)''', line):
                found.setdefault(match.group(1), []).append(f'{path.relative_to(REPO)}:{lineno}')
    return found


def questionnaire():
    '''Return (defined attributes, attributes used per catalog, defined options).'''
    defined = {el.get(DC)[len(BASE):] for el in ET.parse(QUESTIONNAIRE / 'attributes.xml').getroot()
               if el.tag == 'attribute'}
    used = {}
    for path in sorted(QUESTIONNAIRE.glob('mardmo-*-catalog.xml')):
        root = ET.parse(path).getroot()
        attrs = {el.get(DC)[len(BASE):] for el in root.iter('attribute') if el.get(DC)}
        used[path.stem] = attrs
    options = {el.get(DC) for el in ET.parse(QUESTIONNAIRE / 'optionsets.xml').getroot().iter('option')
               if el.get(DC)}
    return defined, used, options


def main():
    defined, used, options = questionnaire()
    used_any = set().union(*used.values())
    attrs, opts = code_attributes(), code_options()
    errors = 0

    missing = sorted(a for a in attrs if a not in defined)
    print(f'== attributes named in the code: {len(attrs)}, defined in attributes.xml: {len(defined)}')
    for a in missing:
        errors += 1
        print(f'ERROR   attribute not defined: {a}')
        for where in attrs[a][:3]:
            print(f'           {where}')

    unused = sorted(a for a in attrs if a in defined and a not in used_any and a not in KNOWN_HIDDEN)
    for a in unused:
        print(f'WARNING attribute defined but in no catalog: {a}')
        for where in attrs[a][:3]:
            print(f'           {where}')

    print(f'== options named in the code: {len(opts)}, defined in optionsets.xml: {len(options)}')
    for o in sorted(o for o in opts if o not in options and o not in KNOWN_INTERNAL):
        errors += 1
        print(f'ERROR   option not defined: {o}')
        for where in opts[o][:3]:
            print(f'           {where}')
    # Keys can also be read through a list of keys (software_reference_ids, …),
    # so only entries that are not in the questionnaire either are leftovers
    _, unused_keys = options_json_usage()
    leftovers = {k: v for k, v in unused_keys.items() if v not in options}
    for key, uri in leftovers.items():
        print(f'INFO    data/options.json entry not read by options[...] and not in the questionnaire: '
              f'{key} ({uri[len(OPTIONS):]})')
    for name in sorted(KNOWN_HIDDEN - set(attrs)):
        print(f'NOTE    KNOWN_HIDDEN entry no longer used by the code: {name}')
    for uri in sorted(KNOWN_INTERNAL - set(opts)):
        print(f'NOTE    KNOWN_INTERNAL entry no longer used by the code: {uri}')

    for catalog, attrs_used in used.items():
        manual = sorted(a for a in attrs_used if a not in attrs)
        print(f'INFO    {catalog}: {len(attrs_used)} attributes, {len(manual)} not named in the code')

    print(f'== {errors} error(s), {len(unused)} warning(s)')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
