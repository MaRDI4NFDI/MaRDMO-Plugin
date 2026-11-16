'''Wikidata quantities of formulas: portal twins, and no Wikidata chains (#166).

A formula or quantity from Wikidata brings the quantities of its defining
formula.  One with a fitting twin on the MaRDI Portal (same Wikidata QID,
a quantity or quantity kind there) becomes the portal item and is filled
from the portal; the others get a page with their name and description
only, so the chain ends there (before, every quantity of every defining
formula was filled from Wikidata: 68 pages for Ohm's law).  The answers of
the portal and Wikidata are given here.
'''
import pytest

from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_items
from MaRDMO.handler_base import portal_twins
from MaRDMO.markers import SECTION_MARKERS
from MaRDMO.model import models
from MaRDMO.model.handlers import Information, use_portal_twins
from MaRDMO.models import Relatant
from MaRDMO.queries import PortalItems
from tests.db.conftest import answer, save

ITEMS = get_items()
CURRENT = Relatant('wikidata:Q29996', 'electric current', 'flow of electric charge')
VOLTAGE = Relatant('wikidata:Q25428', 'voltage', 'difference in electric potential')
RESISTANCE = Relatant('wikidata:Q25358', 'electrical resistance', 'opposition to the passage of an electric current')
OHMS_LAW = ('wikidata:Q41591', "Ohm's law", 'law of electricity')
QUANTITY = {'class': {ITEMS['quantity']}, 'community': set(), 'profile': set()}
SOFTWARE = {'class': {ITEMS['software']}, 'community': set(), 'profile': set()}
MARKERS = (SECTION_MARKERS['model']['quantity'], SECTION_MARKERS['model']['quantity kind'])


@pytest.fixture
def portal(monkeypatch):
    '''The portal knows: current as Q1 (a quantity), voltage as Q2 (software: another kind), resistance not.'''
    asked = []

    def find(wikidata_qids=(), **kwargs):
        asked.append(sorted(wikidata_qids))
        return PortalItems(by_wikidata={'Q29996': 'Q1', 'Q25428': 'Q2', 'Q25358': None},
                           markers={'Q1': QUANTITY, 'Q2': SOFTWARE})
    monkeypatch.setattr('MaRDMO.queries.find_portal_items', find)
    monkeypatch.setattr('MaRDMO.queries.portal_labels',
                        lambda qids, **kwargs: {'Q1': ('electric current', 'rate of flow of electric charge')})
    return asked


def test_only_fitting_twins_replace_wikidata_items(portal):
    twins = portal_twins([CURRENT, VOLTAGE, RESISTANCE, Relatant('mardi:Q7', 'x', 'y')], MARKERS)
    assert twins == {CURRENT.id: Relatant('mardi:Q1', 'electric current', 'rate of flow of electric charge')}
    assert portal == [['Q25358', 'Q25428', 'Q29996']]                 # one lookup, Wikidata items only


def test_a_failed_lookup_keeps_the_wikidata_items(monkeypatch):
    monkeypatch.setattr('MaRDMO.queries.find_portal_items', lambda **kwargs: PortalItems(wikidata_failed=True))
    data = models.MathematicalFormulation(contains_quantity=[CURRENT, RESISTANCE])
    use_portal_twins([data])
    assert data.contains_quantity == [CURRENT, RESISTANCE]


def test_no_lookup_without_wikidata_items(portal):
    data = models.MathematicalFormulation(contains_quantity=[Relatant('mardi:Q7', 'x', 'y')])
    use_portal_twins([data])
    assert portal == []


def test_a_wikidata_formula_brings_its_quantities_without_chain(portal, project, monkeypatch):
    '''Ohm's law: current from the portal (filled there), voltage and resistance as pages without their formulas.'''
    filled = []

    def fetch(items, mardi_query, wikidata_query, entity):
        filled.append(sorted(external_id for _, external_id, _ in items))
        if entity is models.MathematicalFormulation:
            return {external_id: entity() for _, external_id, _ in items}
        return {}                   # the twin has no MathModDB data on the portal (a Wikidata import)
    monkeypatch.setattr('MaRDMO.model.handlers._fetch_by_source', fetch)
    monkeypatch.setattr(models, 'fetch_formula_data', lambda qids: {})
    monkeypatch.setattr(models, 'fetch_formula_data_wikidata', lambda qids: {qid: {
        'formulas': [r'U = R \cdot I'], 'symbols': ['U', 'R', 'I'],
        'contains_quantity': [VOLTAGE, RESISTANCE, CURRENT]} for qid in qids})
    documentation = project('mardmo-model-catalog')
    save(documentation, answer('formulation', 'F1', set_index=0),
         answer('formulation/id', f"{OHMS_LAW[1]} ({OHMS_LAW[2]})", external_id=OHMS_LAW[0], set_index=0))
    Information()._fill_formulation_batch(documentation, [(f"{OHMS_LAW[1]} ({OHMS_LAW[2]})", OHMS_LAW[0], 0)],
                                          'mardmo-model-catalog', set())

    pages = dict(documentation.values.filter(snapshot=None, set_prefix='', attribute__uri=f'{BASE_URI}domain/quantity/id')
                 .values_list('external_id', 'set_index'))
    assert set(pages) == {'mardi:Q1', VOLTAGE.id, RESISTANCE.id}
    # Filled: the formula, then the portal twin; the Wikidata quantities are not
    assert filled == [[OHMS_LAW[0]], ['mardi:Q1']]
    # The symbols refer to the portal twin and the Wikidata quantities
    symbols = documentation.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/formulation/element/quantity')
    assert sorted(symbols.values_list('external_id', flat=True)) == sorted(['mardi:Q1', VOLTAGE.id, RESISTANCE.id])
    # The Wikidata pages have their name and description
    names = dict(documentation.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/quantity/name')
                 .values_list('set_prefix', 'text'))
    assert names[str(pages[VOLTAGE.id])] == 'voltage' and names[str(pages[RESISTANCE.id])] == 'electrical resistance'
    # The twin found nothing to be filled with: it keeps the portal's name
    assert names[str(pages['mardi:Q1'])] == 'electric current'
