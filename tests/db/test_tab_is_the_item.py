'''A tab is the item: its links follow it when its item changes in the interview (#186).

The interview saves the ID of a tab through RDMO's API; every answer that
referred to the previous item then refers to the new one, whatever the
switch.  Several tabs with one item: the links belong to the first of them.
Saves outside the interview (imports, MaRDMO's own writes) move nothing.
MaRDMO's filling from the portal is switched off here.
'''
import pytest
from rdmo.projects.models import Membership

from MaRDMO import router
from MaRDMO.core.constants import BASE_URI
from MaRDMO.core.ids import is_user_id
from tests.db.conftest import answer, save

API = '/api/v1/projects/projects/{}/values/'
MASS = ('user:mass', 'new item')
PORTAL_MASS = ('mardi:Q5', 'mass (property of matter)')
WIKIDATA_MASS = ('wikidata:Q11423', 'mass (property of physical bodies)')


def uri(path):
    return f'{BASE_URI}domain/{path}'


@pytest.fixture
def doc(project, client, django_user_model, monkeypatch):
    '''Quantity tab Q1 (mass, own); a task (own) and a formula (portal) link to it.'''
    for path in ('quantity/id', 'task/id', 'formulation/id'):
        monkeypatch.setitem(router.HANDLER_MAP['mardmo-model-catalog'], uri(path), lambda instance: None)
    documentation = project('mardmo-model-catalog')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    client.force_login(user)
    save(documentation,
         answer('quantity', 'Q1', set_index=0),
         answer('quantity/id', MASS[1], external_id=MASS[0], set_index=0),
         answer('quantity/name', 'mass', set_prefix='0'),
         answer('quantity/description', 'physical quantity', set_prefix='0'),
         answer('task', 'T1', set_index=0),
         answer('task/id', 'new item', external_id='user:task', set_index=0),
         answer('task/quantity-relatant', 'mass (physical quantity)', external_id=MASS[0], set_prefix='0|0'),
         answer('formulation', 'F1', set_index=0),
         answer('formulation/id', "Newton's second law (formula)", external_id='mardi:Q9', set_index=0),
         answer('formulation/element/quantity', 'mass (physical quantity)', external_id=MASS[0], set_prefix='0'))
    return documentation


def choose(client, documentation, item, section='quantity', index=0):
    '''Choose *item* ``(ID, text)`` in the ID dropdown of tab *index*, as the interview saves it.'''
    value = documentation.values.get(attribute__uri=uri(f'{section}/id'), set_prefix='', set_index=index)
    response = client.put(API.format(documentation.pk) + f'{value.pk}/', {
        'attribute': value.attribute_id, 'set_prefix': '', 'set_index': index, 'collection_index': 0,
        'text': item[1], 'external_id': item[0], 'value_type': 'text'}, content_type='application/json')
    assert response.status_code == 200, response.content
    return response.json()


def links(documentation):
    '''``{relation: (ID, text)}`` of the task's relation and the formula's element to the quantity.'''
    return {path: documentation.values.filter(attribute__uri=uri(path)).values_list('external_id', 'text').get()
            for path in ('task/quantity-relatant', 'formulation/element/quantity')}


@pytest.mark.parametrize('item', [PORTAL_MASS, WIKIDATA_MASS])
def test_an_own_item_switched_to_the_portal_or_wikidata_takes_its_links_along(doc, client, item):
    choose(client, doc, item)
    # Also the link on the portal formula's tab: the export adds it to the portal item
    assert links(doc) == {'task/quantity-relatant': item, 'formulation/element/quantity': item}


@pytest.mark.parametrize('first, second', [(PORTAL_MASS, WIKIDATA_MASS), (WIKIDATA_MASS, PORTAL_MASS)])
def test_a_switch_between_portal_and_wikidata_takes_the_links_along(doc, client, first, second):
    choose(client, doc, first)
    choose(client, doc, second)
    assert set(links(doc).values()) == {second}


@pytest.mark.parametrize('item', [PORTAL_MASS, WIKIDATA_MASS])
def test_a_portal_or_wikidata_item_made_a_new_item_takes_its_links_along(doc, client, item):
    choose(client, doc, item)
    new = choose(client, doc, ('not found', 'new item'))['external_id']
    assert is_user_id(new) and new != MASS[0]
    # A new item keeps the name and description of the tab: the texts stay
    assert set(links(doc).values()) == {(new, item[1])}


def test_choosing_new_item_again_keeps_the_item_and_its_links(doc, client):
    assert choose(client, doc, ('not found', 'new item'))['external_id'] == MASS[0]
    assert set(links(doc).values()) == {('user:mass', 'mass (physical quantity)')}


def two_tabs(doc, item):
    '''A second quantity tab (Q2) with *item*, e.g. a copy of a portal item.'''
    save(doc, answer('quantity', 'Q2', set_index=1), answer('quantity/id', item[1], external_id=item[0], set_index=1))


def test_of_two_tabs_with_one_item_the_first_takes_the_links_along(doc, client):
    choose(client, doc, PORTAL_MASS)
    two_tabs(doc, PORTAL_MASS)
    new = choose(client, doc, ('not found', 'new item'))['external_id']
    assert set(links(doc).values()) == {(new, PORTAL_MASS[1])}
    # The second tab is still the portal item, without the links
    assert doc.values.get(attribute__uri=uri('quantity/id'), set_index=1).external_id == PORTAL_MASS[0]


def test_of_two_tabs_with_one_item_a_later_one_moves_nothing(doc, client):
    choose(client, doc, PORTAL_MASS)
    two_tabs(doc, PORTAL_MASS)
    choose(client, doc, ('not found', 'new item'), index=1)
    assert set(links(doc).values()) == {PORTAL_MASS}


def test_a_tab_of_another_section_with_the_item_keeps_the_links(doc, client):
    choose(client, doc, PORTAL_MASS)
    save(doc, answer('task', 'T2', set_index=1), answer('task/id', PORTAL_MASS[1], external_id=PORTAL_MASS[0],
                                                       set_index=1))
    choose(client, doc, WIKIDATA_MASS)
    assert set(links(doc).values()) == {PORTAL_MASS}


def test_switching_to_an_item_of_another_tab_merges_them(doc, client):
    '''Two tabs with one item: the checks report "Same Item as Page" (test_copies.py).'''
    two_tabs(doc, PORTAL_MASS)
    choose(client, doc, PORTAL_MASS)
    assert set(links(doc).values()) == {PORTAL_MASS}


def test_a_tab_never_takes_another_own_id(doc, client):
    '''The interview may send a copied tab's old ID again: the tab keeps its own.'''
    assert choose(client, doc, ('user:other', 'new item'))['external_id'] == MASS[0]
    assert set(links(doc).values()) == {('user:mass', 'mass (physical quantity)')}


def test_saves_outside_the_interview_move_nothing(doc):
    '''An import or MaRDMO's own writes save without the interview's signal.'''
    value = doc.values.get(attribute__uri=uri('quantity/id'), set_index=0)
    value.external_id, value.text = PORTAL_MASS
    value.save()
    assert set(links(doc).values()) == {('user:mass', 'mass (physical quantity)')}


# --- Clearing a tab's item (the links stay with the tab) -----------------------------------------

CLEARED = ('', '')
PARKED = ('tab:quantity:0', 'mass (physical quantity)')


def test_a_cleared_tab_keeps_its_links(doc, client):
    choose(client, doc, CLEARED)
    assert set(links(doc).values()) == {PARKED}


@pytest.mark.parametrize('item', [PORTAL_MASS, WIKIDATA_MASS])
def test_the_item_chosen_after_clearing_takes_the_links(doc, client, item):
    choose(client, doc, CLEARED)
    choose(client, doc, item)
    assert set(links(doc).values()) == {item}


def test_a_new_item_chosen_after_clearing_takes_the_links(doc, client):
    choose(client, doc, CLEARED)
    new = choose(client, doc, ('not found', 'new item'))['external_id']
    assert is_user_id(new) and new != MASS[0]
    assert set(links(doc).values()) == {(new, PARKED[1])}


def test_clearing_a_later_tab_with_the_item_keeps_the_links_with_the_first(doc, client):
    choose(client, doc, PORTAL_MASS)
    two_tabs(doc, PORTAL_MASS)
    choose(client, doc, CLEARED, index=1)
    assert set(links(doc).values()) == {PORTAL_MASS}


def test_deleting_a_cleared_tab_removes_its_links(doc, client):
    '''RDMO gives the number of a deleted last tab to the next new one: nothing may be left for it.'''
    choose(client, doc, CLEARED)
    tab = doc.values.get(attribute__uri=uri('quantity'), set_prefix='', set_index=0)
    assert client.delete(API.format(doc.pk) + f'{tab.pk}/set/').status_code == 204
    assert not doc.values.filter(external_id=PARKED[0]).exists()
    assert not doc.values.filter(attribute__uri__in=[uri('task/quantity-relatant'),
                                                     uri('formulation/element/quantity')]).exists()


def test_the_checks_report_the_tab_without_item_not_the_links(doc, client, monkeypatch):
    from MaRDMO import main  # noqa: PLC0415
    from MaRDMO.model.checks import ModelChecks  # noqa: PLC0415
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    choose(client, doc, CLEARED)
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = doc, None
    answers = provider.get_post_data()[0]
    messages = [str(message) for message in ModelChecks().run(project=doc, data=answers, catalog=str(doc.catalog))]
    assert any('Q1' in message and 'Missing ID' in message for message in messages)
    assert not any('Selected Quantity not found' in message for message in messages)
