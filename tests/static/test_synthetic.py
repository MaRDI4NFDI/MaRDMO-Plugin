'''The synthetic documentations use everything of their catalog (see tools/synthetic).

Every question has an answer, every fixed option is chosen, every option
that takes a text has one, and every dropdown of items has an item of each
source it offers: the MaRDI Portal, Wikidata, and the user's own items.
When the questionnaire gets a question or option, these tests name it, and
the description in tools/synthetic gets it (then build again, see
tests/db/test_synthetic_build.py).
'''
import importlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from MaRDMO.core.searches import PROVIDERS
from tests.db.test_synthetic_build import BUILDS
from tools.synthetic.catalog import DOMAIN, OPTIONS, Catalog

DC = '{http://purl.org/dc/elements/1.1/}uri'
PROJECTS = Path(__file__).parents[1] / 'data' / 'projects'
BUILT = [name for name in sorted(BUILDS) if (PROJECTS / f'{name}.xml').exists()]


def answers(name):
    '''``{attribute key: [(option key, text, external ID)]}`` of the synthetic documentation *name*.'''
    found = {}
    for node in ET.parse(PROJECTS / f'{name}.xml').getroot().find('values'):
        attribute = node.find('attribute').get(DC, '')
        option = node.find('option')
        option = option.get(DC, '') if option is not None else ''
        found.setdefault(attribute.removeprefix(DOMAIN), []).append(
            (option.removeprefix(OPTIONS) if option else '', node.findtext('text') or '',
             node.findtext('external_id') or ''))
    return found


def sources(provider):
    '''The sources of items the dropdown *provider* offers: ``mardi``, ``wikidata``, ``user``.

    The sources it searches: not Wikidata where it has nothing for the class (process steps, #170).
    '''
    search = PROVIDERS[provider]
    offered = set(search.search_sources or ('mardi', 'wikidata'))
    if search.not_found or search.with_answers:
        offered.add('user')
    return offered


@pytest.fixture(scope='module', params=BUILT)
def built(request, questionnaire):
    catalog_name = BUILDS[request.param][0]
    return Catalog.read(questionnaire.path, catalog_name), answers(request.param)


def test_every_question_is_answered(built):
    catalog, found = built
    assert [question.key for question in catalog.questions() if question.attribute not in found] == []


def test_no_answer_outside_the_catalog(built):
    '''MaRDMO writes only answers the catalog has questions for (#168), apart from the
    citation data of publications, which is stored without questions.'''
    catalog, found = built
    known = {question.attribute for question in catalog.questions()} | {page.attribute for page in catalog.pages}
    assert sorted(key for key in found if key not in known and not key.startswith('publication/')) == []


def test_every_option_is_chosen(built):
    catalog, found = built
    missing = [f'{question.key}: {option}' for question in catalog.questions() for option in question.options
               if option not in {chosen for chosen, _, _ in found.get(question.attribute, [])}]
    assert missing == []


def test_every_option_with_a_text_is_used_with_one(built):
    '''Options that take a text (a DOI, a size, a comment) are chosen with their text at least once.

    Pages filled from the MaRDI Portal may choose them without (a "yes" without comment).
    '''
    catalog, found = built
    without = [f'{question.key}: {option}' for question in catalog.questions() for option in question.options
               if option in catalog.inputs
               and not any(chosen == option and text.strip() for chosen, text, _ in found.get(question.attribute, []))]
    assert without == []


# Sources a dropdown offers that have no item of its class yet: {(question, source): why}
UNAVAILABLE = {
    ('processstep/instrument-relatant', 'mardi'): 'the MaRDI Portal has no research tools (instruments) yet',
}


def test_every_dropdown_has_items_of_each_source(built):
    catalog, found = built
    missing = []
    for question in catalog.questions():
        for provider in question.providers:
            used = {external_id.split(':', 1)[0] for _, _, external_id in found.get(question.attribute, [])}
            missing += [f'{question.key}: {source}' for source in sorted(sources(provider) - used)
                        if (question.attribute, source) not in UNAVAILABLE]
    assert missing == []


# --- Every relation arrives in the export ---------------------------------------------------

RELATIONS = {  # catalog: the module whose get_relations() maps relation options on statements
    'mardmo-model-catalog': 'MaRDMO.model.constants',
    'mardmo-model-basics-catalog': 'MaRDMO.model.constants',
    'mardmo-algorithm-catalog': 'MaRDMO.algorithm.constants',
    'mardmo-interdisciplinary-workflow-catalog': 'MaRDMO.workflow.constants',
}
GOLDEN = Path(__file__).parents[1] / 'data' / 'golden'


def values(name):
    '''``[(attribute key, set_prefix, set_index, option URI, external ID)]`` of the documentation *name*.'''
    found = []
    for node in ET.parse(PROJECTS / f'{name}.xml').getroot().find('values'):
        option = node.find('option')
        found.append((node.find('attribute').get(DC, '').removeprefix(DOMAIN), node.findtext('set_prefix') or '',
                      int(node.findtext('set_index') or 0), option.get(DC, '') if option is not None else '',
                      node.findtext('external_id') or ''))
    return found


def statements(payload):
    '''``{(subject, property, object)}: [qualifier values]`` of the payload; items as QIDs or ``Item…`` keys.'''
    def node(reference):
        item = payload.get(reference)
        return item['id'] if item and item.get('id') else reference
    found = {}
    for key, entry in payload.items():
        if key.startswith('ALIAS'):
            continue
        if key.startswith('RELATION'):
            subject = entry['url'].rsplit('/statements', 1)[0].rsplit('/', 1)[-1]
            statement = entry['payload']['statement']
            triples = [(statement['property']['id'], statement['value'].get('content'), statement.get('qualifiers', []))]
        else:
            subject = key
            triples = [(prop, value, qualifiers) for prop, _, value, *rest in entry.get('statements', [])
                       for qualifiers in [rest[0] if rest else []]]
        for prop, value, qualifiers in triples:
            value = node(value) if isinstance(value, str) else json.dumps(value, sort_keys=True)
            found.setdefault((node(subject), prop, value), []).append(
                [qualifier['value'].get('content') for qualifier in qualifiers])
    return found


def nodes(payload):
    '''``{documentation ID: payload node}``: own items by their IDs, portal items by QID, Wikidata items by P12.'''
    found = {}
    for key, item in payload.items():
        if not key.startswith('Item'):
            continue
        for identifier in item.get('user_ids', []):
            found[identifier] = item['id'] or key
        for prop, _, value, *_ in item.get('statements', []):
            if prop == 'P12':
                found[f'wikidata:{value}'] = item['id'] or key
    return found


@pytest.mark.parametrize('name', [name for name in BUILT if (GOLDEN / f'{name}.json').exists()])
def test_every_relation_arrives_in_the_export(name, questionnaire):
    catalog = Catalog.read(questionnaire.path, BUILDS[name][0])
    relations = importlib.import_module(RELATIONS[catalog.name]).get_relations()
    payload = json.loads((GOLDEN / f'{name}.json').read_text(encoding='utf-8'))['payload']
    found, ids = statements(payload), nodes(payload)

    def node(identifier):
        return identifier.split(':', 1)[1] if identifier.startswith('mardi:') else ids.get(identifier, identifier)

    answers = values(name)
    pages = {(attribute.split('/')[0], index): external_id for attribute, prefix, index, _, external_id in answers
             if prefix == '' and attribute.count('/') == 1 and attribute.endswith('/id')}
    missing, checked = [], 0
    for question in catalog.questions():
        if not any(OPTIONS + option in relations for option in question.options):
            continue
        relatants = [sibling.attribute for sibling in question.parent.children
                     if sibling.kind == 'question' and sibling.providers and 'assumption' not in sibling.attribute]
        for attribute, prefix, index, option, _ in answers:
            if attribute != question.attribute or option not in relations:
                continue
            subject = pages[(attribute.split('/')[0], int(prefix.split('|')[0]))]
            prop, extra = (relations[option] + [None])[:2]
            for relatant in [external_id for key, other_prefix, other_index, _, external_id in answers
                             if key in relatants and (other_prefix, other_index) == (prefix, index) and external_id]:
                # Between two portal items the statement is on the portal (MaRDMO filled it from there)
                if subject.startswith('mardi:') and relatant.startswith('mardi:'):
                    continue
                # Stored on the relatant: relations marked "backward", and every relation of a
                # publication ("described by source" on the entity, the role as qualifier)
                reverse = extra == 'backward' or attribute.startswith('publication/')
                one, other = (relatant, subject) if reverse else (subject, relatant)
                qualifier = extra if extra not in (None, 'forward', 'backward') else None
                found_qualifiers = found.get((node(one), prop, node(other)))
                checked += 1
                if found_qualifiers is None or (qualifier and not any(qualifier in q for q in found_qualifiers)):
                    missing.append(f'{one} {option.rsplit("/", 1)[-1]} {other}: {prop}{" " + qualifier if qualifier else ""}')
    assert checked > 0
    assert missing == []
