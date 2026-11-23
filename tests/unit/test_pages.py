'''MaRDMO.project.pages: a relation to a page renders as its name, linked, with the tab (#152).'''
from django.template import Context, Template

from MaRDMO.export.relations import entity_relations, map_entity
from MaRDMO.project.pages import PageRef, page_refs


def render(value):
    return Template('{{ value }}').render(Context({'value': value}))


def test_relation_is_the_linked_name_with_the_tab():
    ref = PageRef('formulation', 3, 'Navier-Stokes equation', 'F4')
    assert ref.label == 'Navier-Stokes equation (F4)'
    assert render(ref) == '<a href="#page-formulation-3">Navier-Stokes equation</a> (F4)'


def test_names_are_escaped():
    assert render(PageRef('task', 0, '<b>a</b>', 'T&1')) == \
        '<a href="#page-task-0">&lt;b&gt;a&lt;/b&gt;</a> (T&amp;1)'


def test_page_without_name_or_tab():
    assert render(PageRef('task', 0, '', 'CT1')) == '<a href="#page-task-0">CT1</a>'
    assert PageRef('task', 0, 'solve', '').label == 'solve'
    assert PageRef('task', 4, '', '').label == 'page 5'


def test_first_page_of_an_id_and_section_order():
    data = {'formulation': {2: {'ID': 'mardi:Q1', 'Name': 'a', 'Tab': 'F3'},
                            5: {'ID': 'mardi:Q1', 'Name': 'a', 'Tab': 'F6'}},
            'quantity': {0: {'ID': 'mardi:Q1', 'Name': 'q', 'Tab': 'QQK1'},
                         1: {'ID': 'mardi:Q2', 'Name': 'r', 'Tab': 'QQK2'}}}
    refs = page_refs(data, ['formulation', 'quantity'])
    assert refs['mardi:Q1'] == PageRef('formulation', 2, 'a', 'F3')
    assert refs['mardi:Q2'] == PageRef('quantity', 1, 'r', 'QQK2')


def test_relations_resolve_to_pages_or_keep_their_id():
    data = {'formulation': {7: {'ID': 'mardi:Q1', 'Name': 'a', 'Tab': 'mass'}},
            'model': {0: {'MFRelatant': {0: {'ID': 'mardi:Q1'}, 1: {'ID': 'user:9'}},
                          'assumption': {0: {0: {'ID': 'mardi:Q1'}, 1: {'ID': 'mardi:Q5'}}}}}}
    entity_relations(data, {'from': 'model', 'to': 'formulation'},
                     {'relation': None, 'old_name': 'MFRelatant', 'new_name': 'RelationMF'},
                     assumption=False, mapping=None)
    map_entity(data, {'from': 'model', 'to': 'formulation'},
               {'old_name': 'assumption', 'new_name': 'assumptionMapped'})
    model = data['model'][0]
    assert model['RelationMF'] == {0: PageRef('formulation', 7, 'a', 'mass'), 1: 'user:9'}
    assert model['assumptionMapped'] == {0: {0: PageRef('formulation', 7, 'a', 'mass'), 1: 'mardi:Q5'}}
