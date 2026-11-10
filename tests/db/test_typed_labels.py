'''A new item's typed text is its label; own items without page get a generic description (#129).'''
from types import SimpleNamespace

import pytest

from MaRDMO import main
from MaRDMO.checks import Checks
from MaRDMO.helpers import basic_dict, describe_items_without_page
from tests.db.conftest import answer, save


def test_the_text_of_an_own_item_is_its_label():
    value = SimpleNamespace(text='Navier-Stokes (incompressible)', external_id='user:1')
    assert basic_dict(value) == {'ID': 'user:1', 'Name': 'Navier-Stokes (incompressible)', 'Description': ''}


def test_the_text_of_a_portal_item_is_split():
    value = SimpleNamespace(text='Python (programming language) [mardi]', external_id='mardi:Q1')
    assert basic_dict(value) == {'ID': 'mardi:Q1', 'Name': 'Python', 'Description': 'programming language'}


def item(identifier, name='x', description=''):
    return {'ID': identifier, 'Name': name, 'Description': description}


def test_own_items_without_page_get_the_description_of_their_kind():
    data = {'software': {0: {'programminglanguage': {0: item('user:1'), 1: item('mardi:Q1', 'Python', 'lang')}}},
            'hardware': {0: {'cpu': {0: item('user:2')}}},
            'processstep': {0: {'MRelatant': {0: {0: item('user:3')}}, 'IRelatant': {0: item('user:4')},
                                'RFRelatant': {0: item('user:5')}}},
            'algorithm': {0: {'PRelatant': {0: item('user:6')}}}}
    describe_items_without_page(data)
    software = data['software'][0]['programminglanguage']
    assert software[0]['Description'] == 'programming language'
    assert software[1]['Description'] == 'lang'
    assert data['hardware'][0]['cpu'][0]['Description'] == 'cpu model'
    process_step = data['processstep'][0]
    assert process_step['MRelatant'][0][0]['Description'] == 'experimental method'
    assert process_step['IRelatant'][0]['Description'] == 'instrument'
    assert process_step['RFRelatant'][0]['Description'] == 'academic discipline'
    assert data['algorithm'][0]['PRelatant'][0]['Description'] == 'algorithmic task'


def test_an_own_item_with_a_page_keeps_its_description():
    '''Tasks of the algorithm catalog have pages; their description is the page's.'''
    data = {'problem': {0: item('user:6', 'solve', 'a task')},
            'algorithm': {0: {'PRelatant': {0: item('user:6', 'solve', 'a task')}}}}
    describe_items_without_page(data)
    assert data['algorithm'][0]['PRelatant'][0]['Description'] == 'a task'


@pytest.fixture
def software(project, monkeypatch):
    '''An algorithm project with two software pages, both programmed in the new language "Python".'''
    documentation = project('mardmo-algorithm-catalog')
    for index in (0, 1):
        save(documentation, answer('software', f'S{index + 1}', set_index=index),
             answer('software/id', 'new item', external_id=f'user:s{index}', set_index=index),
             answer('software/name', f'code {index}', set_prefix=str(index)),
             answer('software/description', f'a code {index}', set_prefix=str(index)),
             answer('software/programming-language-relatant', 'Python', external_id=f'user:py{index}',
                    set_prefix=str(index)))
    return documentation


def answers_of(project):
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    return provider.get_post_data()[0]


def test_preview_and_export_send_one_language_with_the_generic_description(software):
    answers = answers_of(software)
    assert list(answers['programminglanguage'].values()) == [
        {'ID': 'user:py0', 'Name': 'Python', 'Description': 'programming language'}]


def test_the_checks_do_not_ask_for_its_description(software):
    answers = answers_of(software)
    messages = [str(m) for m in Checks().run_algorithm(project=software, data=answers,
                                                       catalog=str(software.catalog))]
    assert not any('Programming Language' in message for message in messages)
