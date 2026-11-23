'''Academic disciplines of the workflow catalog get the markers of research fields (#147).'''
import pytest

from MaRDMO import main
from MaRDMO.core.config import get_items, get_properties, get_url
from MaRDMO.core.markers import SECTION_MARKERS
from MaRDMO.sources.portal import PortalItems
from MaRDMO.workflow.worker import PrepareWorkflow
from tests.db.conftest import answer, save


def test_disciplines_and_research_fields_get_the_same_markers():
    assert SECTION_MARKERS['workflow']['academicdiscipline'] == SECTION_MARKERS['model']['field']


@pytest.fixture
def workflow(project):
    '''A process step in a new discipline and in one from Wikidata.'''
    documentation = project('mardmo-interdisciplinary-workflow-catalog')
    save(documentation,
         answer('processstep', 'PS1', set_index=0),
         answer('processstep/id', 'not found', external_id='user:step', set_index=0),
         answer('processstep/name', 'step', set_prefix='0'),
         answer('processstep/description', 'a step', set_prefix='0'),
         answer('processstep/field-relatant', 'tide studies', external_id='user:tides', set_prefix='0', collection_index=0),
         answer('processstep/field-relatant', 'ecology (study)', external_id='wikidata:Q7150',
                set_prefix='0', collection_index=1))
    return documentation


def test_the_export_gives_disciplines_class_community_and_profile(workflow, monkeypatch):
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: PortalItems())
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = workflow, None
    answers, _ = provider.get_post_data()
    payload, _ = PrepareWorkflow().export(answers, get_url('mardi', 'uri'))
    items, properties = get_items(), get_properties()
    expected = {(properties['instance of'], items['academic discipline']),
                (properties['community'], items['MathModDB']),
                (properties['MaRDI profile type'], items['MaRDI research field profile'])}
    disciplines = [entry for entry in payload.values() if isinstance(entry, dict)
                   and entry.get('label') in ('tide studies', 'ecology')]
    assert len(disciplines) == 2, payload
    for entry in disciplines:
        statements = {(statement[0], statement[2]) for statement in entry.get('statements', [])
                      if isinstance(statement, list) and len(statement) > 2}
        assert expected <= statements, entry
