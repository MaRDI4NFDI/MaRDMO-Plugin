'''Wikidata relatants: portal twins, and no Wikidata chains (#166).

An item MaRDMO fills from Wikidata brings its relatants: the quantities of
its defining formula, the dependencies and programming languages of a
software, the software of an algorithm in a process step, ...  One with a
fitting twin on the MaRDI Portal (same Wikidata QID, of the kind the
relation asks for) becomes the portal item, label and description
included: a relation to it, and a page that is filled from the portal.  The
others stay Wikidata items; their pages get their name and description
only, so the chain ends there (before, every quantity of every defining
formula was filled from Wikidata: 68 pages for Ohm's law).  The answers of
the portal and Wikidata are given here.
'''
import pytest

from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_items
from MaRDMO.handler_base import portal_twins, twin_fields, use_portal_twins
from MaRDMO.markers import SECTION_MARKERS
from MaRDMO.model import models
from MaRDMO.model.handlers import TWINS, Information
from MaRDMO.models import Algorithm, Relatant, Software
from MaRDMO.sources.portal import PortalItems
from MaRDMO.workflow.handlers import _model_uses
from MaRDMO.workflow.models import ProcessStep, ProcessStepUsage
from tests.db.conftest import answer, save
from tests.db.test_hydration_pages import page_of, pages, selected

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
    monkeypatch.setattr('MaRDMO.handler_base.find_portal_items', find)
    monkeypatch.setattr('MaRDMO.handler_base.portal_labels',
                        lambda qids, **kwargs: {'Q1': ('electric current', 'rate of flow of electric charge')})
    return asked


def test_only_fitting_twins_replace_wikidata_items(portal):
    twins = portal_twins([CURRENT, VOLTAGE, RESISTANCE, Relatant('mardi:Q7', 'x', 'y')], MARKERS)
    assert twins == {CURRENT.id: Relatant('mardi:Q1', 'electric current', 'rate of flow of electric charge')}
    assert portal == [['Q25358', 'Q25428', 'Q29996']]                 # one lookup, Wikidata items only


def test_a_failed_lookup_keeps_the_wikidata_items(monkeypatch):
    monkeypatch.setattr('MaRDMO.handler_base.find_portal_items', lambda **kwargs: PortalItems(wikidata_failed=True))
    data = models.MathematicalFormulation(contains_quantity=[CURRENT, RESISTANCE])
    use_portal_twins([data], twin_fields('model', TWINS['formulation']))
    assert data.contains_quantity == [CURRENT, RESISTANCE]


def test_no_lookup_without_wikidata_items(portal):
    data = models.MathematicalFormulation(contains_quantity=[Relatant('mardi:Q7', 'x', 'y')])
    use_portal_twins([data], twin_fields('model', TWINS['formulation']))
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


# Software, a programming language and a model on the portal, and their Wikidata twins
LANGUAGE = {'class': {ITEMS['programming language']}, 'community': set(), 'profile': set()}
MODEL = {'class': {ITEMS['mathematical model']}, 'community': set(), 'profile': set()}
MATPLOTLIB = ('wikidata:Q2985', 'Matplotlib', 'plotting library for Python')
NUMPY = Relatant('wikidata:Q197520', 'NumPy', 'Python library for numerical computing')
TRAITLETS = Relatant('wikidata:Q107380679', 'traitlets', 'Python library')
PYTHON = Relatant('wikidata:Q28865', 'Python', 'general-purpose programming language')
ALGORITHM = Relatant('wikidata:Q12', 'fast Fourier transform', 'algorithm')
LAPTOP = ('wikidata:Q3962', 'laptop', 'portable computer')
CATALOG = 'mardmo-interdisciplinary-workflow-catalog'


@pytest.fixture
def twins(monkeypatch):
    '''The portal has NumPy (Q11, software), Python (Q12, a programming language) and the heat model (Q13).'''
    asked = []
    portal = {'Q197520': ('Q11', SOFTWARE, ('NumPy', 'fundamental package for array computing')),
              'Q28865': ('Q12', LANGUAGE, ('Python', 'programming language')),
              'Q1': ('Q13', MODEL, ('heat model', 'model of heat conduction'))}

    def find(wikidata_qids=(), **kwargs):
        asked.append(sorted(wikidata_qids))
        return PortalItems(by_wikidata={qid: portal[qid][0] if qid in portal else None for qid in wikidata_qids},
                           markers={twin: markers for twin, markers, _ in portal.values()})
    monkeypatch.setattr('MaRDMO.handler_base.find_portal_items', find)
    monkeypatch.setattr('MaRDMO.handler_base.portal_labels', lambda qids, **kwargs: {
        twin: label for twin, _, label in portal.values() if twin in qids})
    return asked


@pytest.fixture
def filled(monkeypatch):
    '''The data of Wikidata and the portal: ``{ID: entity}``; returns the items each lookup fills.'''
    found, calls = {}, []

    def fetch(items, mardi_query, wikidata_query, entity):
        calls.append((entity.__name__, sorted(external_id for _, external_id, _ in items)))
        return {external_id: found.get(external_id, entity()) for _, external_id, _ in items}
    for module in ('MaRDMO.handler_base', 'MaRDMO.workflow.handlers'):
        monkeypatch.setattr(f'{module}._fetch_by_source', fetch)
    return found, calls


def relatants(documentation, section, identifier, attribute):
    return sorted(page_of(documentation, section, identifier, attribute).values_list('external_id', flat=True))


def test_a_wikidata_software_brings_portal_twins_and_no_chain(project, twins, filled):
    '''Matplotlib: NumPy from the portal (filled there), traitlets a page without dependencies, Python from the portal.'''
    from MaRDMO.algorithm.handlers import Information
    found, calls = filled
    found[MATPLOTLIB[0]] = Software(depends_on_software=[NUMPY, TRAITLETS], programmed_in=[PYTHON])
    found[TRAITLETS.id] = Software(depends_on_software=[Relatant('wikidata:Q7', 'six', 'Python library')])
    documentation, item = selected(project, 'mardmo-algorithm-catalog', 'software', MATPLOTLIB)
    Information()._fill_software_batch(documentation, [item], catalog='mardmo-algorithm-catalog')

    assert pages(documentation, 'software') == {MATPLOTLIB[0], 'mardi:Q11', TRAITLETS.id}
    assert relatants(documentation, 'software', MATPLOTLIB[0], 'software/dependency-relatant') == [
        'mardi:Q11', TRAITLETS.id]
    # A relation without page takes the twin too (no duplicate in the preview)
    assert relatants(documentation, 'software', MATPLOTLIB[0], 'software/programming-language-relatant') == [
        'mardi:Q12']
    # Filled: Matplotlib, then the portal twin; traitlets is not (its dependency six never shows up)
    assert calls == [('Software', [MATPLOTLIB[0]]), ('Software', ['mardi:Q11'])]
    assert twins == [['Q107380679', 'Q197520', 'Q28865']]
    # Each page has its name: the portal's for the twin
    assert page_of(documentation, 'software', 'mardi:Q11', 'software/name').get().text == 'NumPy'
    assert page_of(documentation, 'software', TRAITLETS.id, 'software/name').get().text == 'traitlets'
    assert page_of(documentation, 'software', TRAITLETS.id, 'software/description').get().text == 'Python library'


def test_a_wikidata_item_on_a_page_keeps_its_page(project, twins, filled):
    '''NumPy, already a page with its Wikidata ID, is not replaced: the documentation keeps one NumPy.'''
    from MaRDMO.algorithm.handlers import Information
    found, _ = filled
    found[MATPLOTLIB[0]] = Software(depends_on_software=[NUMPY])
    documentation, item = selected(project, 'mardmo-algorithm-catalog', 'software', MATPLOTLIB)
    save(documentation, answer('software', 'S2', set_index=1),
         answer('software/id', 'NumPy (Python library)', external_id=NUMPY.id, set_index=1))
    Information()._entry(documentation.values.get(attribute__uri=f'{BASE_URI}domain/software/id', set_index=0),
                         'Software', Information()._fill_software_batch)

    assert pages(documentation, 'software') == {MATPLOTLIB[0], NUMPY.id}
    assert relatants(documentation, 'software', MATPLOTLIB[0], 'software/dependency-relatant') == [NUMPY.id]
    assert twins == []


def test_the_software_of_an_algorithm_in_a_process_step(project, twins, filled):
    '''A Wikidata process step: the algorithm and laptop get pages without chain, NumPy is the portal's.'''
    from MaRDMO.workflow.handlers import Information
    found, calls = filled
    step = ('wikidata:Q5', 'spectral analysis', 'process step')
    found[step[0]] = ProcessStep(uses_algorithm=[ProcessStepUsage(
        id=ALGORITHM.id, label=ALGORITHM.label, description=ALGORITHM.description,
        qualifier=NUMPY.id, qualifier_label=NUMPY.label, qualifier_description=NUMPY.description,
        hardware=LAPTOP[0], hardware_label=LAPTOP[1], hardware_description=LAPTOP[2],
        parameters=None, doi=[], url=[])])
    found[ALGORITHM.id] = Algorithm(implemented_by=[TRAITLETS])
    documentation, item = selected(project, CATALOG, 'processstep', step)
    Information()._fill_process_step_batch(documentation, [item], catalog=CATALOG)

    assert relatants(documentation, 'processstep', step[0], 'processstep/software-relatant') == ['mardi:Q11']
    assert relatants(documentation, 'processstep', step[0], 'processstep/algorithm-relatant') == [ALGORITHM.id]
    assert relatants(documentation, 'processstep', step[0], 'processstep/hardware-relatant') == [LAPTOP[0]]
    assert pages(documentation, 'software') == {'mardi:Q11'}
    assert pages(documentation, 'algorithm') == {ALGORITHM.id}
    assert pages(documentation, 'hardware') == {LAPTOP[0]}
    # Filled: the step and the portal's NumPy; not the Wikidata algorithm (traitlets never shows up)
    assert calls == [('ProcessStep', [step[0]]), ('Software', ['mardi:Q11'])]
    assert page_of(documentation, 'algorithm', ALGORITHM.id, 'algorithm/name').get().text == ALGORITHM.label


def test_the_models_of_a_workflow(twins):
    '''A Wikidata model with a twin becomes the portal's; its task (no twin) stays.'''
    uses = _model_uses(['wikidata:Q1 || heat model || model || wikidata:Q2 || heat task || task',
                        'wikidata:Q197520 || NumPy || library ||  ||  || '], set())
    assert [(use.id, use.label, use.qualifier) for use in uses] == [
        ('mardi:Q13', 'heat model', 'wikidata:Q2'),
        ('wikidata:Q197520', 'NumPy', '')]          # NumPy's twin is software, not a model
