'''Items that exist on the MaRDI Portal already, and the markers of existing items (#141).'''
import pytest

import MaRDMO.queries as queries
from MaRDMO.duplicates import Duplicate, decide, item_source, look_up
from MaRDMO.getters import get_items, get_properties
from MaRDMO.oauth2 import DuplicateOnPortal, OauthProviderMixin
from MaRDMO.markers import SECTION_MARKERS, allowed, contradictions
from MaRDMO.payload import DocumentationProblem, GeneratePayload, PortalUnavailable
from MaRDMO.publication.worker import PublicationExport
from MaRDMO.queries import PortalItems, find_portal_items

ITEMS = get_items()


def payload_of(items, found, monkeypatch):
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: found)
    payload = GeneratePayload(
        url='https://portal.example.org', user_items=items,
        wikibase={'items': ITEMS, 'properties': get_properties(), 'relations': {}},
        dependency={key: set() for key in items})
    return payload


NEW = {'ID': 'user:a', 'Name': 'alpha', 'Description': 'first', 'orcid': '', 'zbmath': '', 'issn': ''}
FROM_WIKIDATA = {'ID': 'wikidata:Q7150', 'Name': 'ecology', 'Description': 'new wording',
                 'orcid': '', 'zbmath': '', 'issn': ''}


def test_all_duplicates_are_reported_at_once(monkeypatch):
    '''Label and description of a new item, the Wikidata QID of a Wikidata item (any label).'''
    found = PortalItems(by_label={('alpha', 'first'): 'Q1', ('ecology', 'new wording'): None},
                        by_wikidata={'Q7150': 'Q60093'})
    payload = payload_of({'Item0000000001': NEW, 'Item0000000002': FROM_WIKIDATA}, found, monkeypatch)
    with pytest.raises(DocumentationProblem) as error:
        payload.process_items()
    assert len(error.value.args) == 2
    assert 'Q1' in error.value.args[0] and 'rename' in error.value.args[0]
    assert 'Q60093' in error.value.args[1] and 'Q7150' in error.value.args[1]


def test_new_items_without_duplicates_are_created(monkeypatch):
    payload = payload_of({'Item0000000001': NEW}, PortalItems(by_label={('alpha', 'first'): None}), monkeypatch)
    payload.process_items()
    assert payload.state.dictionary['Item0000000001']['id'] == ''


def test_a_failed_label_lookup_does_not_stop_the_export(monkeypatch):
    '''The portal rejects exact duplicates itself, and the export links those.'''
    payload = payload_of({'Item0000000001': NEW}, PortalItems(label_failed=True), monkeypatch)
    payload.process_items()


def test_a_failed_wikidata_lookup_stops_the_export(monkeypatch):
    '''The portal would accept a second item with the same Wikidata QID.'''
    payload = payload_of({'Item0000000001': FROM_WIKIDATA}, PortalItems(wikidata_failed=True), monkeypatch)
    with pytest.raises(PortalUnavailable):
        payload.process_items()


# --- markers of existing portal items

def subject(markers, known=True, existing=True):
    payload = GeneratePayload(url='https://portal.example.org', dependency={},
                              wikibase={'items': ITEMS, 'properties': get_properties(), 'relations': {}})
    payload.state.dictionary = {'Item0000000001': {'id': 'Q9' if existing else ''}}
    payload.state.subject_item = 'Item0000000001'
    payload.portal_markers, payload.markers_known = {'Q9': markers}, known
    return payload


def marks(**kinds):
    return {'class': set(kinds.get('classes', ())), 'community': set(kinds.get('community', ())),
            'profile': set(kinds.get('profile', ()))}


DISCIPLINE, SOFTWARE = ITEMS['academic discipline'], ITEMS['software']
MATHMODDB, MATHALGODB = ITEMS['MathModDB'], ITEMS['MathAlgoDB']


@pytest.mark.parametrize('markers, kind, value, expected', [
    (marks(), 'class', DISCIPLINE, True),                                    # unclassified item
    (marks(classes=[DISCIPLINE]), 'class', DISCIPLINE, True),                # its own class
    (marks(classes=[SOFTWARE]), 'class', DISCIPLINE, False),                 # another MaRDMO class
    (marks(classes=['Q999999']), 'class', SOFTWARE, True),                   # a class MaRDMO does not use
    (marks(classes=[ITEMS['linear model']]), 'class', ITEMS['mathematical model'], True),  # same family
    (marks(), 'community', MATHMODDB, True),
    (marks(community=[MATHMODDB]), 'community', MATHMODDB, True),
    (marks(community=[MATHALGODB]), 'community', MATHMODDB, False),
    (marks(profile=['Q1']), 'profile', 'Q2', False),
])
def test_existing_items_get_only_missing_markers_that_do_not_contradict(markers, kind, value, expected):
    assert allowed(kind, value, markers) is expected


class Worker(PublicationExport):
    catalog = 'model'


def statements(payload):
    """The (property, value) of the marker statements given to the subject."""
    sent = []
    payload.add_answer = lambda verb, object_and_type, **kwargs: sent.append((verb, object_and_type[0]))
    Worker()._add_common_metadata(payload, 'field')
    return sent


def test_new_items_get_every_marker():
    properties = get_properties()
    assert statements(subject(marks(classes=[SOFTWARE]), existing=False)) == [
        (properties['instance of'], DISCIPLINE), (properties['community'], MATHMODDB),
        (properties['MaRDI profile type'], ITEMS['MaRDI research field profile'])]


def test_an_existing_item_gets_only_the_markers_allowed():
    properties = get_properties()
    assert statements(subject(marks(classes=[DISCIPLINE], community=[MATHALGODB]))) == [
        (properties['instance of'], DISCIPLINE), (properties['MaRDI profile type'], ITEMS['MaRDI research field profile'])]


def test_without_known_markers_an_existing_item_gets_none():
    assert statements(subject(None, known=False)) == []


def test_a_contradiction_names_the_kinds():
    reuse = SECTION_MARKERS['model']['field']
    assert contradictions(reuse, marks()) == []
    assert contradictions(reuse, marks(classes=[SOFTWARE], community=[MATHMODDB], profile=['Q1'])) == ['class', 'profile']


# --- the lookup

@pytest.fixture
def portal(monkeypatch):
    '''Answers SPARQL queries of find_portal_items; records the queries.'''
    sent = []

    def answer(query, endpoint, strict=False, waits=(), deadline=None):
        sent.append(query)
        if 'rdfs:label' in query:
            return [{'item': {'value': 'https://portal/entity/Q60093'}, 'label': {'value': 'ecology'},
                     'description': {'value': 'study'}}] if '"ecology"@en' in query else []
        if 'VALUES ?wikidata' in query:
            return [{'item': {'value': 'https://portal/entity/Q60093'}, 'wikidata': {'value': 'Q7150'}}]
        return [{'item': {'value': 'https://portal/entity/Q60093'}, 'class': {'value': 'https://portal/entity/Q1'}}]
    monkeypatch.setattr(queries, 'query_sparql', answer)
    return sent


def test_the_lookup_compares_label_and_description_exactly(portal):
    found = find_portal_items(pairs=[('ecology', 'study'), ('Ecology', 'study')], wikidata_qids=['wikidata:Q7150'])
    assert found.by_label == {('ecology', 'study'): 'Q60093', ('Ecology', 'study'): None}
    assert found.by_wikidata == {'Q7150': 'Q60093'}
    assert found.markers == {'Q60093': {'class': {'Q1'}, 'community': set(), 'profile': set()}}


def test_items_without_description_are_not_compared(portal):
    assert find_portal_items(pairs=[('alpha', ''), ('beta', 'No Description Provided!')]).by_label == {}


def test_results_are_reused(portal):
    '''The preview looks them up, the export takes them from there; markers are asked again.'''
    find_portal_items(pairs=[('ecology', 'study')])
    asked = len(portal)
    assert find_portal_items(pairs=[('ecology', 'study')]).by_label == {('ecology', 'study'): 'Q60093'}
    assert [query for query in portal[asked:] if 'rdfs:label' in query] == []


# --- what the preview offers (duplicates.decide)

def duplicate(source='not found', **item):
    return Duplicate({'ID': 'user:a', 'Name': 'alpha', 'Description': 'first', **item}, source, 'Q9', 'label')


def test_unknown_markers_offer_no_reuse():
    assert decide(duplicate(), PortalItems(), {'user:a': {'field'}}, 'model')[0] == 'unknown'


def test_the_sections_of_merged_pages_count_together():
    '''Two pages the export merges: the markers of both must fit.'''
    item = duplicate(user_ids=['user:a', 'user:b'])
    found = PortalItems(markers={'Q9': marks(community=[MATHMODDB])})
    assert decide(item, found, {'user:a': {'programminglanguage'}}, 'algorithm') == ('reuse', [])
    action, reasons = decide(item, found, {'user:a': {'programminglanguage'}, 'user:b': {'problem'}}, 'algorithm')
    assert action == 'rename' and reasons == ['It belongs to MathModDB; MaRDMO would add MathAlgoDB.']


def test_an_item_without_markers_may_always_become_the_portal_item():
    '''E.g. a Wikidata item used in relations only.'''
    assert decide(duplicate('wikidata'), PortalItems(markers={'Q9': marks(classes=[SOFTWARE])}), {}, 'model')[0] == 'reuse'


@pytest.mark.parametrize('value, source', [
    ({'ID': 'mardi:Q1'}, 'mardi'),
    ({'ID': 'wikidata:Q1'}, 'wikidata'),
    ({'ID': 'user:a'}, 'not found'),
    ({'ID': 'user:a', 'kind': 'journal'}, 'journal'),
    ({'ID': 'user:a', 'kind': 'author', 'orcid': '0000', 'zbmath': ''}, 'author'),
    ({'ID': 'user:a', 'kind': 'author', 'orcid': '', 'zbmath': ''}, None),     # not created
    ({'ID': ''}, None),
])
def test_item_source(value, source):
    assert item_source(value) == source


# --- authors and journals: decided in the background (duplicates._resolve_parts)

ORCID = '0000-0002-1825-0097'


def part(kind, identifier, name, description, **fields):
    return {'ID': identifier, 'Name': name, 'Description': description, 'kind': kind,
            'orcid': '', 'zbmath': '', 'issn': '', **fields}


def resolve(items, *answers, monkeypatch):
    """look_up with the portal answering *answers* one after the other (the second: rule 3)."""
    answers = iter(answers)
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: next(answers))
    found, duplicates = look_up([(item_source(item), item) for item in items], (), None)
    assert duplicates == []      # never shown to the user
    return found


def test_a_part_with_the_same_wikidata_qid_is_the_portal_item(monkeypatch):
    author = part('author', 'wikidata:Q1', 'Max Müller', 'researcher')
    resolve([author], PortalItems(by_wikidata={'Q1': 'Q11'}), monkeypatch=monkeypatch)
    assert author['use'] == 'Q11'


def test_a_new_part_with_its_identifier_in_the_description_is_the_portal_item(monkeypatch):
    author = part('author', 'user:a', 'Josiah Carberry', f'scientist (ORCID iD {ORCID})', orcid=ORCID)
    resolve([author], PortalItems(by_label={('Josiah Carberry', f'scientist (ORCID iD {ORCID})'): 'Q12'}),
            monkeypatch=monkeypatch)
    assert author['use'] == 'Q12'


def test_the_same_name_and_description_alone_does_not_make_the_same_author(monkeypatch):
    """A Wikidata author "Max Müller (researcher)": created with its Wikidata QID in the description."""
    author = part('author', 'wikidata:Q1', 'Max Müller', 'researcher')
    resolve([author], PortalItems(by_label={('Max Müller', 'researcher'): 'Q13'}),
            PortalItems(by_label={('Max Müller', 'researcher (Wikidata QID Q1)'): None}), monkeypatch=monkeypatch)
    assert 'use' not in author and author['create_as'] == 'researcher (Wikidata QID Q1)'


def test_the_orcid_comes_before_the_wikidata_qid_and_an_existing_such_item_is_used(monkeypatch):
    author = part('author', 'wikidata:Q1', 'Max Müller', 'researcher', orcid=ORCID)
    named = ('Max Müller', f'researcher (ORCID iD {ORCID})')
    resolve([author], PortalItems(by_label={('Max Müller', 'researcher'): 'Q13'}),
            PortalItems(by_label={named: 'Q14'}, markers={'Q14': marks()}), monkeypatch=monkeypatch)
    assert author['use'] == 'Q14'


@pytest.mark.parametrize('classes, decision', [
    ([], ('use', 'Q15')),
    ([ITEMS['scientific journal']], ('use', 'Q15')),
    ([ITEMS['human']], ('omit', True)),
])
def test_a_journal_without_identifier_uses_a_portal_journal_of_its_title(monkeypatch, classes, decision):
    journal = part('journal', 'user:j', 'Mathematics', 'scientific journal')
    resolve([journal], PortalItems(by_label={('Mathematics', 'scientific journal'): 'Q15'},
                                   markers={'Q15': marks(classes=classes)}), monkeypatch=monkeypatch)
    assert journal.get(decision[0]) == decision[1]


def test_the_export_uses_creates_or_leaves_out_parts_as_decided(monkeypatch):
    used = part('author', 'user:a', 'A', f'scientist (ORCID iD {ORCID})', orcid=ORCID)
    named = part('author', 'wikidata:Q1', 'B', 'researcher')
    left = part('journal', 'user:j', 'C', 'scientific journal')
    found = [PortalItems(by_label={('A', used['Description']): 'Q12', ('B', 'researcher'): 'Q13',
                                   ('C', 'scientific journal'): 'Q15'},
                         markers={'Q12': marks(), 'Q13': marks(), 'Q15': marks(classes=[ITEMS['human']])}),
             PortalItems()]
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: found.pop(0))
    payload = GeneratePayload(url='https://portal.example.org', dependency={},
                              user_items={'Item1': used, 'Item2': named, 'Item3': left},
                              wikibase={'items': ITEMS, 'properties': get_properties(), 'relations': {}})
    payload.process_items()
    items = payload.state.dictionary
    assert items['Item1']['id'] == 'Q12'
    assert items['Item2']['id'] == '' and items['Item2']['description'] == 'researcher (Wikidata QID Q1)'
    assert 'Item3' not in items


# --- the same label and description twice in a documentation

def test_an_own_item_named_like_a_wikidata_item_of_the_documentation_stops_the_export(monkeypatch):
    """The portal takes one; before, it linked the second silently to the first."""
    own = {**NEW, 'Name': 'ecology', 'Description': 'new wording'}
    payload = payload_of({'Item0000000001': FROM_WIKIDATA, 'Item0000000002': own}, PortalItems(), monkeypatch)
    with pytest.raises(DocumentationProblem) as error:
        payload.process_items()
    assert 'Wikidata item Q7150 of this documentation' in error.value.args[0]


def test_the_preview_offers_to_rename_it():
    other = dict(FROM_WIKIDATA)
    action, reasons = decide(Duplicate(NEW, 'not found', '', 'documentation', other), PortalItems(), {}, 'model')
    assert action == 'rename' and 'Q7150' in reasons[0]


# --- an item created on the portal between the check and the upload (HTTP 422)

class Response:
    status_code = 422

    def json(self):
        return {'code': 'data-policy-violation', 'context': {
            'violation': 'item-label-description-duplicate', 'violation_context': {'conflicting_item_id': 'Q77'}}}


@pytest.mark.parametrize('cls, kind', [('Quantity', None), ('Author', 'author')])
def test_a_portal_duplicate_at_upload_stops_the_export(cls, kind):
    jsons = {'Item1': {'id': '', 'label': 'mass', 'description': 'physical quantity', 'class': cls}}
    with pytest.raises(DuplicateOnPortal) as error:
        OauthProviderMixin()._handle_policy_violation(Response(), 'Item1', jsons)
    assert (error.value.qid, error.value.part) == ('Q77', kind)
    assert jsons['Item1']['id'] == ''


def test_the_message_says_what_to_do():
    own = DuplicateOnPortal('mass', 'physical quantity', 'Q77')
    assert own.message(sent=False) == (
        'The MaRDI Portal did not create "mass" (physical quantity): an item with this label and description '
        'now exists there (Q77). It was not there when MaRDMO checked before the export, so it was probably '
        'created in the meantime. Nothing was sent to the MaRDI Portal. Open the preview again: under '
        '"Already on the MaRDI Portal" you can use Q77 or rename your item. Then export again; the export '
        'adds the rest.')
    # After something was created, the result page lists it
    assert 'Nothing was sent' not in own.message(sent=True)
    author = DuplicateOnPortal('Max Müller', 'researcher', 'Q77', 'author').message(sent=True)
    assert author.endswith('Please export again: MaRDMO then handles the author itself.')
    assert 'preview' not in author


def test_the_job_stores_the_message(monkeypatch):
    stored = {}
    monkeypatch.setattr('MaRDMO.oauth2._progress_store', stored)
    jsons = {'Item1': {'id': '', 'label': 'mass', 'description': 'physical quantity',
                       'payload': {'item': {'labels': {'en': 'mass'}}}, 'statements': []}}
    OauthProviderMixin()._finish_job(None, 'job', None, jsons, jsons,
                                     DuplicateOnPortal('mass', 'physical quantity', 'Q77'), 0, 1)
    assert stored['job']['phase'] == 'error' and 'Nothing was sent' in stored['job']['error']
