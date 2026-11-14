"""Publications by DOI against the duplicate rules of #141: real lookups, then faked portal entries.

Run with pytest in the plugin's test environment (tests/settings.py: the
MaRDI Portal, a throwaway database with the questionnaire), not in the RDMO
app, so the local configuration does not matter:

    cd ~/Work/MaRDMO-Plugin
    QUESTIONNAIRE=~/Work/MaRDMO-Questionnaire/catalog \\
        pytest dev-tests/duplicates_dois.py --force-enable-socket -p no:cacheprovider -q

Read-only: nothing is posted (the upload of scenario "upload" is faked).

Per DOI (lists ITEMS of items.json, default all four publication lists), a
project with a model of the user's own and the publication ("documents"):

1. real: the preview (citation lookup) and the export payload, with the
   portal as it is.  The preview section must not list authors or
   journals; the export must not stop for them; the sections whose markers
   the export gave must be those the preview would use.
2. faked portal entries, on top of the real answers (the portal's answers
   are reused, so these runs ask nothing):

   - p12:            a Wikidata author/journal has a portal twin (P12): used
   - mardmo:         a new author/journal with its identifier in MaRDMO's
                     description is on the portal: used, gets the identifier
   - namesake:       a Wikidata author/journal has a namesake without
                     identifiers: created with "(<identifier>)" in the description
   - namesake-named: ... and exactly that item exists: used
   - journal-title:  a new journal without identifier, a portal journal of
                     its title: used
   - journal-person: ... that portal item is a person: left out, no "published in"
   - journal-unknown: ... its markers could not be looked up: left out
   - documentation:  an own item with the label and description of the
                     publication (if it is a Wikidata item): reported by
                     preview and export
   - upload:         HTTP 422 "duplicate" at the first item, in the middle,
                     and at an author/journal: the export stops with the
                     right message; only what was created gets portal IDs

Results: results/<OUT>/<number>-<doi>.json and .html (the preview, for
preview_compare.py) and summary.json; a DOI with a broken rule fails.

Environment: ITEMS (comma-separated lists of items.json), ONLY (numbers),
LIMIT, OUT (default duplicates-dois).
"""
import datetime
import json
import os
import re
import time
import traceback
from types import SimpleNamespace

import pytest
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.test import RequestFactory
from django.template.loader import render_to_string
from rdmo.projects.models import Project, Value
from rdmo.projects.signals import value_created
from rdmo.questions.models import Catalog

from MaRDMO import duplicates, main
from MaRDMO import oauth2
from MaRDMO.checks import Checks
from MaRDMO.constants import BASE_URI, CATALOG_TEMPLATE_MAP
from MaRDMO.getters import get_items, get_item_url, get_properties, get_url
from MaRDMO.helpers import replace_in_dict, topological_order, unique_items, value_editor
from MaRDMO.payload import DocumentationProblem, GeneratePayload
from MaRDMO.queries import PortalItems
from tests.conftest import questionnaire  # noqa: F401
from tests.db.conftest import django_db_setup  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
LISTS = os.environ.get('ITEMS', 'publication_sources,publication_sources_2,publication_sources_3,'
                                'publication_duplicates').split(',')
OUT = os.path.join(HERE, 'results', os.environ.get('OUT', 'duplicates-dois'))
PAUSE = 2
MARDMO = 'https://rdmo.mardi4nfdi.de/terms/options/mardmo/'
DOI_OPTION = 'https://rdmo.mardi4nfdi.de/terms/options/doi'
MODEL = ('Test model for publications', 'model the publication documents')
FAKE, FAKE_NAMED = 'Q999999901', 'Q999999902'
ITEMS = get_items()
PROPERTIES = get_properties()
EMPTY = {'class': set(), 'community': set(), 'profile': set()}

entries = []
for name in LISTS:
    entries += [{**entry, 'list': name} for entry in json.load(open(os.path.join(HERE, 'items.json')))[name]]
ENTRIES = list(enumerate(entries, 1))
if os.environ.get('ONLY'):
    ENTRIES = [(n, e) for n, e in ENTRIES if str(n) in os.environ['ONLY'].split(',')]
if os.environ.get('LIMIT'):
    ENTRIES = ENTRIES[:int(os.environ['LIMIT'])]
os.makedirs(OUT, exist_ok=True)


# --- the project

def answer(project, path, signal=False, **info):
    value, _ = value_editor(project=project, uri=f'{BASE_URI}domain/{path}', info=info)
    if signal:
        value_created.send(sender=Value, instance=value)
    return value


def documentation(doi):
    project = Project.objects.create(title='TEMP duplicates dois', site=Site.objects.get_current(),
                                     catalog=Catalog.objects.get(uri__endswith='mardmo-model-catalog'))
    answer(project, 'model', text='MM1', set_index=0)
    answer(project, 'model/id', signal=True, text='new item', external_id='not found', set_index=0)
    answer(project, 'model/name', text=MODEL[0], set_prefix='0', set_index=0)
    answer(project, 'model/description', text=MODEL[1], set_prefix='0', set_index=0)
    answer(project, 'publication', text='P1', set_index=0)
    answer(project, 'publication/id', signal=True, text='new item', external_id='not found', set_index=0)
    answer(project, 'publication/reference', option=DOI_OPTION, text=doi, set_index=0, collection_index=0)
    answer(project, 'publication/entity-relation', option=f'{MARDMO}documents', set_prefix='0', set_index=0)
    model_id = project.values.get(attribute__uri=f'{BASE_URI}domain/model/id').external_id
    answer(project, 'publication/entity-relatant', set_prefix='0', set_index=0, collection_index=0,
           text=f'{MODEL[0]} ({MODEL[1]})', external_id=model_id)
    return project


def provider_of(project):
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    return provider


# --- the export, observed

class Observed:
    '''The export of a project: payload, the decisions on authors and journals, the payload object.'''

    def __init__(self, monkeypatch):
        self.payloads, self.parts = [], []
        init, resolve = GeneratePayload.__init__, duplicates._resolve_parts
        observed = self

        def remember(payload, *args, **kwargs):
            init(payload, *args, **kwargs)
            observed.payloads.append(payload)

        def decide(parts, *args, **kwargs):
            resolve(parts, *args, **kwargs)
            observed.parts = parts
        monkeypatch.setattr(GeneratePayload, '__init__', remember)
        monkeypatch.setattr(duplicates, '_resolve_parts', decide)

    def decisions(self):
        return [{'kind': item['kind'], 'source': source, 'ID': item['ID'], 'Name': item['Name'],
                 'Description': item['Description'],
                 **{key: item[key] for key in ('use', 'create_as', 'omit') if key in item}}
                for source, item in self.parts]


def export(project, prepare):
    '''``(answers, result)``: checks and export of *project* as the export button would run them.'''
    answers, _ = provider_of(project).get_post_data()
    result = {'messages': [str(m) for m in Checks().run_model(project=project, data=answers,
                                                              catalog=str(project.catalog)) or []]}
    try:
        result['payload'], result['dependency'] = prepare.export(answers, get_url('mardi', 'uri'))
    except (ValueError, KeyError) as error:
        result['export message'] = [str(argument) for argument in error.args]
    return answers, result


def parts_of(answers):
    return [(duplicates.item_source(item), item) for item in unique_items(answers)[0].values()
            if item.get('kind') and duplicates.item_source(item)]


# --- the faked portal

class Portal:
    '''find_portal_items: the real answers (asked once per question), plus faked entries.'''

    def __init__(self, monkeypatch):
        self.real, self.asked = duplicates.find_portal_items, {}
        self.reset()
        monkeypatch.setattr(duplicates, 'find_portal_items', self.find)

    def reset(self):
        self.by_label, self.by_wikidata, self.markers, self.markers_failed = {}, {}, {}, False

    def find(self, pairs=(), wikidata_qids=(), marker_qids=(), waits=(), deadline=None):
        pairs = list(pairs)
        if pairs and all(pair in self.by_label for pair in pairs):
            found = PortalItems()      # a faked question (rule 3): nothing real to ask
        else:
            key = json.dumps([sorted(map(list, pairs)), sorted(wikidata_qids), sorted(marker_qids)])
            if key not in self.asked:
                self.asked[key] = self.real(pairs=pairs, wikidata_qids=wikidata_qids, marker_qids=marker_qids,
                                            waits=waits, deadline=deadline)
            found = self.asked[key]
        found = PortalItems(by_label=dict(found.by_label), by_wikidata=dict(found.by_wikidata),
                            markers={qid: dict(markers) for qid, markers in found.markers.items()},
                            label_failed=found.label_failed, wikidata_failed=found.wikidata_failed,
                            markers_failed=found.markers_failed or self.markers_failed)
        found.by_label.update({pair: qid for pair, qid in self.by_label.items() if pair in pairs})
        found.by_wikidata.update({qid.split(':', 1)[-1]: twin for qid, twin in self.by_wikidata.items()
                                  if qid in wikidata_qids})
        found.markers.update(self.markers)
        return found


def identifier(item):
    return duplicates.part_identifier(item)


def statements_on(payload, qid, prop):
    """Statements *prop* the export adds to the portal item *qid* (addressed by its Item key until the upload)."""
    names = {qid} | {key for key, value in payload.items() if key.startswith('Item') and value.get('id') == qid}
    return [entry for key, entry in payload.items()
            if key.startswith('RELATION') and any(f'/items/{name}/' in entry.get('url', '') for name in names)
            and entry.get('payload', {}).get('statement', {}).get('property', {}).get('id') == prop]


def scenarios(parts, answers):
    '''``[(name, setup, check)]`` for the parts of this publication.'''
    found = []
    wikidata = [item for source, item in parts if source == 'wikidata']
    new = [item for source, item in parts if source in ('author', 'journal')]
    with_id = [item for item in new if identifier(item) and identifier(item)[1].lower() in item['Description'].lower()]
    plain_journals = [item for item in new if item['kind'] == 'journal' and not identifier(item)]

    if wikidata:
        item = wikidata[0]
        found.append(('p12', lambda portal, item=item: portal.by_wikidata.update({item['ID']: FAKE}),
                      lambda run, item=item: expect(run, item, use=FAKE)))
        named = (item['Name'], f"{item['Description']} ({identifier(item)[0]} {identifier(item)[1]})")
        found.append(('namesake', lambda portal, item=item: portal.by_label.update({(item['Name'], item['Description']): FAKE}),
                      lambda run, item=item, named=named: expect(run, item, create_as=named[1])))
        found.append(('namesake-named', lambda portal, item=item, named=named: portal.by_label.update(
                          {(item['Name'], item['Description']): FAKE, named: FAKE_NAMED}),
                      lambda run, item=item: expect(run, item, use=FAKE_NAMED)))
    if with_id:
        item = with_id[0]
        found.append(('mardmo', lambda portal, item=item: portal.by_label.update({(item['Name'], item['Description']): FAKE}),
                      lambda run, item=item: expect(run, item, use=FAKE, identifier_statement=True)))
    if plain_journals:
        item = plain_journals[0]
        pair = (item['Name'], item['Description'])

        def journal(classes, failed=False):
            def setup(portal):
                portal.by_label[pair] = FAKE
                if failed:
                    portal.markers_failed = True
                else:
                    portal.markers[FAKE] = {**EMPTY, 'class': set(classes)}
            return setup
        found.append(('journal-title', journal([ITEMS['scientific journal']]), lambda run, item=item: expect(run, item, use=FAKE)))
        found.append(('journal-person', journal([ITEMS['human']]), lambda run, item=item: expect(run, item, omit=True)))
        found.append(('journal-unknown', journal([], failed=True), lambda run, item=item: expect(run, item, omit=True)))
    return found


def expect(run, item, use=None, create_as=None, omit=False, identifier_statement=False):
    '''Problems of the export *run* for the author/journal *item* (empty: as the rules say).'''
    problems = []
    if 'export message' in run:
        return [f"export stopped: {run['export message']}"]
    decided = next((part for part in run['parts'] if part['ID'] == item['ID'] and part['Name'] == item['Name']), None)
    if decided is None:
        return ['not decided']
    for key, wanted in (('use', use), ('create_as', create_as), ('omit', omit or None)):
        if decided.get(key) != wanted:
            problems.append(f'{key}: {decided.get(key)!r}, expected {wanted!r}')
    named = [value for key, value in run['payload'].items() if key.startswith('Item') and value.get('label') == item['Name']]
    if use and not any(value.get('id') == use for value in named):
        problems.append(f'payload item: {[value.get("id") for value in named]}, expected {use}')
    if create_as and not any(value.get('description') == create_as and not value.get('id') for value in named):
        problems.append(f'payload item: {[(value.get("id"), value.get("description")) for value in named]}')
    if omit:
        published_in = [statement for value in run['payload'].values() if isinstance(value, dict)
                        for statement in value.get('statements', [])
                        if isinstance(statement, list) and statement and statement[0] == PROPERTIES['published in']]
        relations = [value for key, value in run['payload'].items() if key.startswith('RELATION')
                     and value.get('payload', {}).get('statement', {}).get('property', {}).get('id')
                     == PROPERTIES['published in']]
        if published_in or relations:
            problems.append('"published in" without its journal')
    if identifier_statement:
        prop = {'ORCID iD': 'ORCID iD', 'zbMath ID': 'zbMATH author ID', 'ISSN': 'ISSN'}[identifier(item)[0]]
        if not statements_on(run['payload'], use, PROPERTIES[prop]):
            problems.append(f'no {prop} statement on {use}')
    return problems


# --- the upload, faked

class Response:
    status_code = 422

    def json(self):
        return {'code': 'data-policy-violation', 'context': {
            'violation': 'item-label-description-duplicate', 'violation_context': {'conflicting_item_id': FAKE}}}


def upload(project, payload, dependency, stop, monkeypatch):
    '''The upload of *payload*, with the portal refusing the item *stop* as a duplicate.'''
    store, created = {}, []
    monkeypatch.setattr(oauth2, '_progress_store', store)
    monkeypatch.setattr(oauth2, 'connection', SimpleNamespace(close=lambda: None))
    mixin = oauth2.OauthProviderMixin()

    def post(key, jsons, token):
        item = jsons.get(key)
        if not item:
            return jsons
        if key.startswith('Item') and item.get('id'):
            return replace_in_dict(jsons, key, item['id'])
        if key == stop:
            mixin._handle_policy_violation(Response(), key, jsons)
        if key.startswith('Item'):
            item['id'] = f'Q99999{len(created):04d}'
            created.append(key)
            return replace_in_dict(jsons, key, item['id'])
        item['id'] = 'statement'
        return jsons
    monkeypatch.setattr(mixin, '_post_data', post)
    mixin._background_post(RequestFactory().get('/'), 'token', json.loads(json.dumps(payload)), topological_order(dependency),
                           'job', project)
    return store['job'], created


def upload_cases(payload, dependency):
    order = [key for key in topological_order(dependency) if key in payload and not payload[key].get('id')]
    if not order:
        return []
    parts = [key for key in order if payload[key].get('class') in ('Author', 'Journal')]
    cases = {'first': order[0], 'middle': order[len(order) // 2]}
    if parts:
        cases['part'] = parts[0]
    return list(cases.items())


# --- the test

@pytest.mark.parametrize('number, entry', ENTRIES, ids=[f"{n:03d}-{e['doi']}" for n, e in ENTRIES])
def test_doi(number, entry, db, monkeypatch):
    time.sleep(PAUSE)
    cache.clear()
    result = {'doi': entry['doi'], 'group': entry['group'], 'list': entry['list'],
              'time': str(datetime.datetime.now()), 'problems': []}
    problems = result['problems']
    html = ''
    try:
        observed = Observed(monkeypatch)
        portal = Portal(monkeypatch)
        project = documentation(entry['doi'])
        prepare = main.PrepareModel()

        # 1. real
        provider = provider_of(project)
        answers, options = provider.get_post_data('preview')
        result['answers preview'] = answers
        html = render_to_string(CATALOG_TEMPLATE_MAP['mardmo-model-catalog'], {
            'answers': answers, 'option': options, 'title': project.title,
            'mardiURI': get_item_url('mardi'), 'wikidataURI': get_item_url('wikidata')})
        report = duplicates.preview_duplicates(project, answers, prepare)
        result['preview rows'] = [(row.duplicate.item['Name'], row.duplicate.qid, row.action) for row in report.rows]
        problems += [f'preview lists the {row.duplicate.item["kind"]} {row.duplicate.item["Name"]}'
                     for row in report.rows if row.duplicate.item.get('kind')]
        publication = next(iter(answers.get('publication', {}).values()), {})
        result['publication'] = {key: publication.get(key) for key in ('ID', 'Name', 'Description', 'entrytype')}

        answers, run = export(project, prepare)
        result['answers'], result['messages'] = answers, run['messages']
        run['parts'] = observed.decisions()
        result['real'] = {'parts': run['parts'], 'export message': run.get('export message')}
        if 'export message' in run:
            # A stop is fine for the user's own items (e.g. a real duplicate), never for a part
            names = {item['Name'] for _, item in parts_of(answers)}
            problems += [f'export stopped for a part: {message}' for message in run['export message']
                         if any(name and name in message for name in names)]
        else:
            result['payload'] = run['payload']
            payload_object = observed.payloads[-1]
            omitted = {part['ID'] for part in run['parts'] if part.get('omit')}
            expected = {key: value for key, value in prepare.marker_sections(answers).items() if key not in omitted}
            if expected != payload_object.marked:
                problems.append(f'marker sections: preview {expected} != export {payload_object.marked}')

        # 2. faked portal entries; the rest of the export's portal checks are not needed
        monkeypatch.setattr(GeneratePayload, 'check_existing_relations', lambda self, *args, **kwargs: None)
        monkeypatch.setattr(GeneratePayload, 'merge_qualifiers', lambda self, *args, **kwargs: None)
        result['scenarios'] = {}
        for name, setup, check in scenarios(parts_of(answers), answers):
            portal.reset()
            setup(portal)
            _, fake = export(project, prepare)
            fake['parts'] = observed.decisions()
            found = check(fake)
            result['scenarios'][name] = found or 'ok'
            problems += [f'{name}: {problem}' for problem in found]

        # documentation: an own item named like the publication from Wikidata
        if (publication.get('ID') or '').startswith('wikidata:'):
            portal.reset()
            answer(project, 'field', text='AD1', set_index=0)
            answer(project, 'field/id', signal=True, text='new item', external_id='not found', set_index=0)
            answer(project, 'field/name', text=publication['Name'], set_prefix='0', set_index=0)
            answer(project, 'field/description', text=publication['Description'], set_prefix='0', set_index=0)
            _, same = export(project, prepare)
            rows = duplicates.preview_duplicates(project, provider_of(project).get_post_data()[0], prepare).rows
            ok = (any('of this documentation' in message for message in same.get('export message', []))
                  and any(row.duplicate.rule == 'documentation' for row in rows))
            result['scenarios']['documentation'] = 'ok' if ok else [same.get('export message'), len(rows)]
            if not ok:
                problems.append(f"documentation: {same.get('export message')}")
            project.values.filter(attribute__uri__startswith=f'{BASE_URI}domain/field').delete()

        # upload: the real payload, the portal refusing one item as a duplicate
        if 'payload' in result:
            result['scenarios']['upload'] = {}
            for case, stop in upload_cases(run['payload'], run['dependency']):
                job, created = upload(project, run['payload'], run['dependency'], stop, monkeypatch)
                entry_item = run['payload'][stop]
                part = {'Author': 'author', 'Journal': 'journal'}.get(entry_item.get('class'))
                found = []
                if not job.get('done') or job.get('phase') not in ('error', 'partial'):
                    found.append(f'phase {job.get("phase")}')
                message = job.get('error') or ''
                if f'"{entry_item["label"]}"' not in message or FAKE not in message:
                    found.append(f'message: {message[:120]}')
                if part and f'handles the {part} itself' not in message:
                    found.append('author/journal message')
                if not part and 'Already on the MaRDI Portal' not in message:
                    found.append('own item message')
                if (job.get('phase') == 'error') != ('Nothing was sent' in message):
                    found.append(f"'Nothing was sent' with phase {job.get('phase')}")
                if len(job.get('ids', [])) != len(created):
                    found.append(f"{len(job.get('ids', []))} items reported, {len(created)} created")
                result['scenarios']['upload'][case] = found or 'ok'
                problems += [f'upload {case}: {problem}' for problem in found]
    except Exception:
        result['error'] = traceback.format_exc()
        problems.append(result['error'].strip().splitlines()[-1])
    finally:
        Project.objects.filter(title='TEMP duplicates dois').delete()
        name = f"{number:03d}-{re.sub(r'[^A-Za-z0-9.]+', '_', entry['doi'])[:60]}"
        open(os.path.join(OUT, f'{name}.html'), 'w').write(html)
        json.dump(result, open(os.path.join(OUT, f'{name}.json'), 'w'), indent=1, default=str)
    assert not problems, problems
