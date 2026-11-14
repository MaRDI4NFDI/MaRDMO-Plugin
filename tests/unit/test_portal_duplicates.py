'''Items that exist on the MaRDI Portal already, and the markers of existing items (#141).'''
import pytest

import MaRDMO.queries as queries
from MaRDMO.getters import get_items, get_properties
from MaRDMO.payload import DocumentationProblem, GeneratePayload, PortalUnavailable
from MaRDMO.publication.worker import PublicationExport
from MaRDMO.queries import PortalItems, find_portal_items

ITEMS = get_items()


def payload_of(items, found, monkeypatch):
    monkeypatch.setattr('MaRDMO.payload.find_portal_items', lambda **kwargs: found)
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


@pytest.mark.parametrize('markers, kind, value, allowed', [
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
def test_existing_items_get_only_missing_markers_that_do_not_contradict(markers, kind, value, allowed):
    assert PublicationExport._marker_allowed(subject(markers), kind, value) is allowed


def test_new_items_get_every_marker():
    assert PublicationExport._marker_allowed(subject(marks(classes=[SOFTWARE]), existing=False), 'class', DISCIPLINE)


def test_without_known_markers_an_existing_item_gets_none():
    assert not PublicationExport._marker_allowed(subject(None, known=False), 'class', DISCIPLINE)


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
