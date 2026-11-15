'''Workflow answers the export would drop are reported instead (found with the staging test).

A CPU entry with occurrence and cores but no CPU model, and a usage block
with only parameters (algorithm or method path), were exported without them
and without a message.
'''
import pytest
from django.template.loader import render_to_string

from MaRDMO.checks import Checks
from MaRDMO.problems import attach
from MaRDMO.workflow.worker import PrepareWorkflow

SOFTWARE = {'ID': 'mardi:Q1', 'Name': 'solver', 'Description': 'a solver'}


@pytest.fixture
def checks():
    return Checks()


def hardware(cpu=None):
    answers = {'hardware': {0: {'ID': 'user:machine', 'Name': 'machine', 'Description': 'a machine', 'nodes': '1',
                                'Tab': 'HW1',
                                'number-of-cpu': {0: '2'}, 'cores': {0: '8'}}}}
    if cpu:
        answers['hardware'][0]['cpu'] = {0: cpu}
    return PrepareWorkflow().preview(answers)


def test_cpu_entry_without_model_is_reported(checks):
    checks.hardware(None, hardware())
    assert ['Missing CPU Model' in str(e) for e in checks.err] == [True]


def test_cpu_entry_with_model_passes(checks):
    checks.hardware(None, hardware({'ID': 'user:cpu', 'Name': 'CPU X', 'Description': 'a CPU'}))
    assert checks.err == []


def test_preview_shows_the_missing_cpu_model(checks):
    answers = hardware()
    checks.hardware(None, answers)
    attach(answers, checks.err)
    html = render_to_string('MaRDMO/workflowTemplate.html', {'answers': answers, 'option': {}})
    assert '<strong class="mardmo-error">Missing CPU Model</strong>' in html


@pytest.mark.parametrize('parameter, pairs', [
    ('algorithm-parameter', 'algorithm_software_pairs'),
    ('method-parameter', 'method_instrument_pairs'),
])
def test_block_with_only_parameters_is_a_usage(parameter, pairs):
    '''The parameter of block 1 belongs to no algorithm (method): the block is shown and checked.'''
    answers = {'processstep': {0: {'ID': 'user:step', 'Name': 'step', 'Description': 'a step',
                                   'RelationA': {'0|0': SOFTWARE}, 'RelationS': {0: SOFTWARE},
                                   parameter: {1: {0: 'tolerance = 0.1'}}}}}
    blocks = PrepareWorkflow().preview(answers)['processstep'][0][pairs]
    assert blocks[-1]['has_primary'] is False
    assert blocks[-1]['parameters'] == 'tolerance = 0.1'
