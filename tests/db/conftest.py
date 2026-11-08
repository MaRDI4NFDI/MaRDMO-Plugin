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
from rdmo.projects.models import Project, Value
from rdmo.projects.signals import value_created
from rdmo.questions.models import Catalog

from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_questions
from MaRDMO.helpers import value_editor
from tests.recordings import record, replay

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
    '''Answers of the external services for the recording *name* (see tests/recordings.py).'''
    saves, missing = [], []

    def use(name):
        if os.environ.get('RECORD') == '1':
            saves.append(record(monkeypatch, name))
        else:
            replay(monkeypatch, name, missing)
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
