'''Hydration gives related items their page as the interview does (#169).

A software MaRDMO fills from the MaRDI Portal or Wikidata writes its
dependencies, and each gets a page of its own, as when the user selects a
dependency (before, the export created a Wikidata dependency without
class).  A method of a process step goes with its instrument only:
hardware goes with algorithms.  The portal's answers are given here.
'''
import pytest

from MaRDMO.core.constants import BASE_URI
from MaRDMO.core.models import Relatant, Software
from MaRDMO.sources.portal import PortalItems
from MaRDMO.workflow.models import ProcessStep, ProcessStepUsage
from tests.db.conftest import answer, save

MATPLOTLIB_INLINE = ('wikidata:Q107380685', 'matplotlib-inline', 'Python library')
TRAITLETS = Relatant('wikidata:Q107380679', 'traitlets', 'Python library')


@pytest.fixture(autouse=True)
def no_twins(monkeypatch):
    '''The portal has no twins of the Wikidata items (#166, see test_portal_twins).'''
    monkeypatch.setattr('MaRDMO.handler_base.find_portal_items', lambda **kwargs: PortalItems())


def given(monkeypatch, module, data):
    '''The SPARQL lookups of *module* find *data* (``{ID: entity}``) and nothing else.'''
    def fetch(items, mardi_query, wikidata_query, entity):
        return {external_id: data[external_id] for _, external_id, _ in items if external_id in data}
    monkeypatch.setattr(f'{module}._fetch_by_source', fetch)


def pages(project, section):
    return set(project.values.filter(snapshot=None, set_prefix='', attribute__uri=f'{BASE_URI}domain/{section}/id')
               .values_list('external_id', flat=True))


def page_of(project, section, identifier, attribute):
    index = project.values.get(snapshot=None, set_prefix='', attribute__uri=f'{BASE_URI}domain/{section}/id',
                               external_id=identifier).set_index
    return project.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/{attribute}',
                                 set_prefix__startswith=str(index))


def selected(project, catalog, section, item):
    documentation = project(catalog)
    identifier, label, description = item
    save(documentation, answer(section, f'{section} 1', set_index=0),
         answer(f'{section}/id', f'{label} ({description})', external_id=identifier, set_index=0))
    return documentation, (f'{label} ({description})', identifier, 0)


def test_a_dependency_gets_its_page(project, monkeypatch):
    from MaRDMO.algorithm.handlers import Information
    given(monkeypatch, 'MaRDMO.handler_base', {MATPLOTLIB_INLINE[0]: Software(depends_on_software=[TRAITLETS]),
                                               TRAITLETS.id: Software()})
    documentation, item = selected(project, 'mardmo-algorithm-catalog', 'software', MATPLOTLIB_INLINE)
    Information()._fill_software_batch(documentation, [item], catalog='mardmo-algorithm-catalog')
    assert pages(documentation, 'software') == {MATPLOTLIB_INLINE[0], TRAITLETS.id}
    assert [value.external_id for value in page_of(documentation, 'software', MATPLOTLIB_INLINE[0],
                                                   'software/dependency-relatant')] == [TRAITLETS.id]
    assert page_of(documentation, 'software', TRAITLETS.id, 'software/name').get().text == 'traitlets'


def test_a_method_goes_with_its_instrument_only(project, monkeypatch):
    from MaRDMO.workflow.handlers import Information
    method = ProcessStepUsage(
        id='mardi:Q7278483', label='method of exhaustion', description='primitive way of calculating area',
        qualifier='wikidata:Q196538', qualifier_label='microscope', qualifier_description='instrument',
        hardware='mardi:Q6487066', hardware_label='Lenovo IdeaPad Flex 5 14ARE05', hardware_description='laptop',
        parameters=None, doi=[], url=[])
    step = ('mardi:Q1', 'measuring', 'a process step')
    given(monkeypatch, 'MaRDMO.workflow.handlers', {step[0]: ProcessStep(uses_method=[method])})
    documentation, item = selected(project, 'mardmo-interdisciplinary-workflow-catalog', 'processstep', step)
    Information()._fill_process_step_batch(documentation, [item], catalog='mardmo-interdisciplinary-workflow-catalog')
    assert [value.external_id for value in page_of(documentation, 'processstep', step[0],
                                                   'processstep/method-relatant')] == [method.id]
    assert [value.external_id for value in page_of(documentation, 'processstep', step[0],
                                                   'processstep/instrument-relatant')] == [method.qualifier]
    assert not page_of(documentation, 'processstep', step[0], 'processstep/hardware-relatant').exists()
    assert pages(documentation, 'hardware') == set()
