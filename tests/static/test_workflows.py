'''The release workflow publishes nothing before the tests pass, and the release only after PyPI.

Zenodo archives every published GitHub release, so the release must be the
last step.  A tag push is a "push" event, so tests.yml is told explicitly to
run every combination.
'''
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).parents[2] / '.github' / 'workflows'


def load(name):
    workflow = yaml.safe_load((WORKFLOWS / name).read_text(encoding='utf-8'))
    # YAML 1.1 reads the key "on" as True
    workflow['on'] = workflow.pop(True, workflow.get('on'))
    return workflow


@pytest.fixture(scope='module')
def publish():
    return load('pypi-publish.yml')


def needs(job):
    value = job.get('needs', [])
    return {value} if isinstance(value, str) else set(value)


def test_started_by_a_version_tag_or_by_hand(publish):
    assert publish['on'].keys() == {'push', 'workflow_dispatch'}
    assert publish['on']['push'] == {'tags': ['v*']}


def test_tests_run_every_combination_against_the_questionnaire_release(publish):
    tests = publish['jobs']['tests']
    assert tests['uses'] == './.github/workflows/tests.yml'
    assert needs(tests) >= {'check', 'questionnaire'}
    assert tests['with'] == {'full_matrix': True, 'questionnaire_ref': '${{ needs.questionnaire.outputs.tag }}'}


def test_pypi_after_the_tests_only_for_tags_with_trusted_publishing(publish):
    pypi = publish['jobs']['pypi']
    assert needs(pypi) >= {'check', 'tests'}
    assert pypi['if'] == "github.event_name == 'push'"
    assert pypi['environment'] == 'pypi'
    assert pypi['permissions'] == {'id-token': 'write'}
    upload = pypi['steps'][-1]['uses']
    assert upload.startswith('pypa/gh-action-pypi-publish@v')
    assert 'secrets.' not in (WORKFLOWS / 'pypi-publish.yml').read_text(encoding='utf-8')


def test_release_is_published_last(publish):
    release = publish['jobs']['release']
    assert needs(release) == {'pypi'}
    # jobs that publish anything: only pypi and release, and release waits for pypi
    writes = {name for name, job in publish['jobs'].items()
              if job.get('permissions', {}).get('contents') == 'write' or 'environment' in job}
    assert writes == {'pypi', 'release'}


def test_tests_take_the_inputs_of_the_release():
    tests = load('tests.yml')
    inputs = tests['on']['workflow_call']['inputs']
    assert inputs['full_matrix'] == {'type': 'boolean', 'default': False}
    assert inputs['questionnaire_ref'] == {'type': 'string', 'default': ''}
    matrix = tests['jobs']['tests']['strategy']['matrix']
    assert all('!inputs.full_matrix' in matrix[key] for key in ('python', 'rdmo'))
    step = next(s for s in tests['jobs']['tests']['steps'] if s.get('id') == 'questionnaire')
    assert 'inputs.questionnaire_ref' in step['run']


def test_actions_are_kept_up_to_date():
    '''An outdated action (pypi-publish 1.12.4) once carried a critical security alert.'''
    config = yaml.safe_load((WORKFLOWS.parent / 'dependabot.yml').read_text(encoding='utf-8'))
    assert {'package-ecosystem': 'github-actions', 'directory': '/'}.items() <= config['updates'][0].items()
