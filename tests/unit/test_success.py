'''The data of the export result page (MaRDMO.success, #138): links, grouping and the graph.'''
import pytest

from MaRDMO.success import group_by_class, object_url, result_graph, split_statements


@pytest.mark.parametrize('prop, obj, obj_qid, url', [
    ('DOI', '10.1000/x', '', 'https://doi.org/10.1000/x'),
    ('ORCID iD', '0000-0001', '', 'https://orcid.org/0000-0001'),
    ('described at URL', 'https://example.org', '', 'https://example.org'),
    ('described at URL', 'javascript:alert(1)', '', ''),       # never a link
    ('DOI', '10.1000/x', 'Q5', ''),                              # a portal item needs no link
    ('contains', 'mass', '', ''),
])
def test_object_url(prop, obj, obj_qid, url):
    assert object_url(prop, obj, obj_qid) == url


def statement(subject, subject_qid, prop, obj, obj_qid='', unit=('', '')):
    return [subject, subject_qid, prop, obj, obj_qid, [], unit[0], unit[1], False]


JOB = {
    'ids': [['Unknown', 'odd', 'Q3'], ['Quantity', 'mass', 'Q1'], ['Mathematical Model', 'model', 'Q2']],
    'statements': [
        statement('mass', 'Q1', 'community', 'MathModDB', 'Q90'),          # standard, on a new item: not counted
        statement('old', 'Q50', 'community', 'MathModDB', 'Q90'),          # standard, on an existing item: counted
        statement('model', 'Q2', 'contains', 'mass', 'Q1'),
        statement('mass', 'Q1', 'amount', '+8', unit=('metre', 'Q92')),
        statement('old', 'Q50', 'uses', 'model', 'Q2'),
    ],
}


def test_statements_go_to_their_items():
    by_item, relations, standard = split_statements(JOB, {'Q1', 'Q2', 'Q3'})
    assert [s['prop'] for s in by_item['Q1']] == ['amount'] and [s['prop'] for s in by_item['Q2']] == ['contains']
    assert [r['subject_qid'] for r in relations] == ['Q50'] and standard == 1


def test_classes_in_their_order_then_the_others():
    groups = group_by_class(JOB['ids'], {})
    assert [cls for cls, _ in groups] == ['Mathematical Model', 'Quantity', 'Unknown']


def test_the_graph():
    by_item, relations, _ = split_statements(JOB, {'Q1', 'Q2', 'Q3'})
    graph = result_graph(group_by_class(JOB['ids'], by_item), relations, 'https://portal/Item:')
    nodes = {node['id']: node for node in graph['nodes']}
    # A created item stays 'new' when a statement refers to it later
    assert nodes['Q1']['node_type'] == 'new' and nodes['Q2']['node_type'] == 'new'
    assert nodes['Q50']['node_type'] == 'item' and nodes['Q92']['node_type'] == 'item'
    assert nodes['_lit_0'] == {'id': '_lit_0', 'label': '+8', 'node_type': 'literal', 'cls': '', 'url': ''}
    edges = {(edge['source'], edge['label'], edge['target']) for edge in graph['edges']}
    assert edges == {('Q2', 'contains', 'Q1'), ('Q1', 'amount', '_lit_0'), ('_lit_0', 'unit', 'Q92'),
                     ('Q50', 'uses', 'Q2')}
