'''The test database for tests/db: RDMO's tables with the MaRDMO questionnaire.

The questionnaire (QUESTIONNAIRE, see tests/conftest.py) is imported once per
test session with RDMO's import, as an admin would import it; every test
runs in a transaction that is rolled back.  Answers are saved without
signals (bulk_create), so MaRDMO's handlers, which would ask the portal,
only run where a test sends a signal itself (:func:`select`, with the
answers of the portal from a recording, :func:`portal`).
'''
import os

import pytest
from django.contrib.sites.models import Site
from django.utils import timezone
from rdmo.core.xml import parse_xml_to_elements
from rdmo.domain.models import Attribute
from rdmo.management.imports import import_elements
from rdmo.options.models import Option
from rdmo.projects.models import Membership, Project, Value
from rdmo.projects.signals import value_created
from rdmo.questions.models import Catalog

from MaRDMO.core.constants import BASE_URI
from MaRDMO.core.config import get_questions
from MaRDMO.project.writes import value_editor
from MaRDMO.sources.portal import PortalItems
from tests.support.recordings import record, replay

# Referenced elements first; the catalogs use all of them
ORDER = ['attributes.xml', 'optionsets.xml', 'conditions.xml']


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker, questionnaire):
    files = ORDER + sorted(path.name for path in questionnaire.path.glob('*-catalog.xml'))
    with django_db_blocker.unblock():
        for name in files:
            elements, errors = parse_xml_to_elements(xml_file=str(questionnaire.path / name))
            assert not errors, f'{name}: {errors}'
            problems = {element['uri']: (element['errors'], element['warnings'])
                        for element in import_elements(elements)
                        if element['errors'] or element['warnings']}
            assert not problems, f'{name}: {problems}'


@pytest.fixture
def project(db):
    '''An empty project of a MaRDMO catalog: ``project('mardmo-model-catalog')``.'''
    def create(catalog):
        return Project.objects.create(title='test', catalog=Catalog.objects.get(uri__endswith=catalog),
                                      site=Site.objects.get_current())
    return create


def answer(path, text='', option=None, **fields):
    '''An unsaved answer of the attribute *path* (e.g. ``quantity/id``); *option* is an option path.'''
    return Value(attribute=Attribute.objects.get(uri=f'{BASE_URI}domain/{path}'), text=text,
                 option=Option.objects.get(uri=f'{BASE_URI}options/{option}') if option else None, **fields)


def save(project, *answers):
    '''Save *answers* to *project* without signals.'''
    now = timezone.now()
    for value in answers:
        value.project, value.created, value.updated = project, now, now
    Value.objects.bulk_create(answers)


@pytest.fixture
def portal(monkeypatch):
    '''Answers of the external services from the recordings *names* (see tests/support/recordings.py).

    Recording stores the requests that the earlier recordings do not have
    in the last one.
    '''
    saves, missing = [], []

    def use(*names):
        if os.environ.get('RECORD') == '1':
            saves.append(record(monkeypatch, names))
        else:
            replay(monkeypatch, names, missing)
    yield use
    for save_recording in saves:
        save_recording()
    assert not missing, f'requests not recorded: {missing}'


def select(project, qkey, item_type, external_id, text, set_index=0):
    '''Select an item on a page as the interview does: its page, its ID answer, then the signal.'''
    questions = get_questions(qkey)[item_type]
    value_editor(project=project, uri=f'{BASE_URI}{questions["uri"]}',
                 info={'text': f'{item_type} {set_index + 1}', 'set_index': set_index})
    value, _ = value_editor(project=project, uri=f'{BASE_URI}{questions["ID"]["uri"]}',
                            info={'text': text, 'external_id': external_id, 'set_index': set_index})
    value_created.send(sender=Value, instance=value)
    return value


@pytest.fixture
def white(project, portal, client, django_user_model, monkeypatch):
    '''white_2006, imported, with an owner logged in; offline and without duplicates on the portal.'''
    from tests.db.test_export import imported
    monkeypatch.setattr('MaRDMO.tex_check.check_formulas', lambda formulas: {})
    monkeypatch.setattr('MaRDMO.model.checks.check_formulas', lambda formulas: {})
    # The preview looks up the publication; the recorded portal has no answers for it
    monkeypatch.setattr('MaRDMO.publication.worker.PublicationRetriever.get_information',
                        lambda self, project, snapshot, answers: answers)
    # Nothing of it is on the portal already (the lookup by label changes with the answers)
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: PortalItems())
    portal('export_white_2006')
    documentation = imported(project, 'white_2006')
    user = django_user_model.objects.create_user('owner', password='owner')
    Membership.objects.create(project=documentation, user=user, role='owner')
    client.force_login(user)
    return documentation


def without_description(documentation, section, index):
    '''Delete the short description of the page *index* of *section* (a problem the checks report).'''
    documentation.values.filter(attribute__uri=f'{BASE_URI}domain/{section}/description',
                                set_prefix=str(index)).delete()
