'''Workflow answers the export would drop are reported instead (found with the staging test).

A CPU entry with occurrence and cores but no CPU model, and a usage block
with only parameters (algorithm or method path), were exported without them
and without a message.
'''
import pytest
from django.template.loader import render_to_string

import MaRDMO.checks.workflow as workflow_checks
from MaRDMO.checks import Checks
from MaRDMO.workflow.worker import PrepareWorkflow

SOFTWARE = {'ID': 'mardi:Q1', 'Name': 'solver', 'Description': 'a solver'}


class Page:
    text = 'HW1'


class Values:
    def filter(self, **kwargs):
        return self

    def get(self, **kwargs):
        return Page()


class Project:
    values = Values()


@pytest.fixture
def checks(monkeypatch):
    monkeypatch.setattr(workflow_checks.Attribute.objects, 'get', lambda **kwargs: None)
    return Checks()


def hardware(cpu=None):
    answers = {'hardware': {0: {'ID': 'user:machine', 'Name': 'machine', 'Description': 'a machine', 'nodes': '1',
                                'number-of-cpu': {0: '2'}, 'cores': {0: '8'}}}}
    if cpu:
        answers['hardware'][0]['cpu'] = {0: cpu}
    return PrepareWorkflow().preview(answers)


def test_cpu_entry_without_model_is_reported(checks):
    checks.hardware(Project(), hardware())
    assert ['Missing CPU Model' in str(e) for e in checks.err] == [True]


def test_cpu_entry_with_model_passes(checks):
    checks.hardware(Project(), hardware({'ID': 'user:cpu', 'Name': 'CPU X', 'Description': 'a CPU'}))
    assert checks.err == []


def test_preview_shows_the_missing_cpu_model():
    answers = hardware()
    html = render_to_string('MaRDMO/workflowTemplate.html', {'answers': answers, 'option': {}})
    assert 'MISSING CPU MODEL' in html


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
