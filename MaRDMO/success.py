'''The result page of an export: what was created, grouped, listed and drawn as a graph.

The export job stores the created items (``ids``: ``[class, name, QID]``)
and the statements it added (``statements``, see
:func:`~MaRDMO.upload.collect_statements`).  :func:`split_statements` sorts
the statements to their items, :func:`group_by_class` orders the items,
and :func:`result_graph` builds the graph of the page.
'''
from collections import defaultdict

from django.utils.translation import gettext_noop as N_

from .core.constants import (
    DOI_BASE_URL,
    ISSN_BASE_URL,
    MORWIKI_BASE_URL,
    ORCID_BASE_URL,
    QUDT_CONSTANT_URL,
    QUDT_QUANTITYKIND_URL,
    SWMATH_BASE_URL,
    WIKIDATA,
    ZBMATH_AUTHOR_BASE_URL,
)
from .validators import url_problem

CLASS_ORDER = [
    N_('Mathematical Model'), N_('Research Problem'), N_('Formula'), N_('Computational Task'),
    N_('Quantity'), N_('Algorithm'), N_('Algorithmic Task'), N_('Software'), N_('Benchmark'),
    N_('Workflow'), N_('Process Step'), N_('Hardware'), N_('CPU Model'), N_('Dataset'),
    N_('Experimental Method'), N_('Experimental Equipment'), N_('Academic Discipline'),
    N_('Programming Language'), N_('Publication'), N_('Author'), N_('Journal'),
]
'''Classes of the items on the result page, in this order; others follow.'''

OBJECT_URLS = {
    'Wikidata QID': WIKIDATA['entity'],
    'DOI': DOI_BASE_URL,
    'swMath work ID': SWMATH_BASE_URL,
    'MORwiki ID': MORWIKI_BASE_URL,
    'QUDT quantity kind ID': QUDT_QUANTITYKIND_URL,
    'QUDT constant ID': QUDT_CONSTANT_URL,
    'ORCID iD': ORCID_BASE_URL,
    'zbMATH author ID': ZBMATH_AUTHOR_BASE_URL,
    'ISSN': ISSN_BASE_URL,
}
'''Properties whose value is an identifier, and the URL it is appended to.'''

URL_PROPERTIES = ('described at URL', 'source code repository URL', 'URL')
'''Properties whose value is a URL the user entered.'''

STANDARD_PROPERTIES = {'community', 'MaRDI profile type'}
'''Properties of the standard statements: not listed, those on existing items counted.'''


def object_url(prop, obj, obj_qid):
    '''A link for the value *obj* of property *prop*, or ``''``.

    A portal item (*obj_qid*) needs no external link.  An identifier links
    to its page (:data:`OBJECT_URLS`); a URL the user entered only if it is
    http(s) (no ``javascript:`` etc.).
    '''
    if obj_qid:
        return ''
    if prop in OBJECT_URLS:
        return f'{OBJECT_URLS[prop]}{obj}'
    if prop in URL_PROPERTIES:
        return obj if not url_problem(obj) else ''
    return ''


def split_statements(job, created_qids):
    '''Sort the statements of *job* to the created items and the relations to existing ones.

    Each statement and qualifier gets the link of its value (``obj_url``,
    :func:`object_url`).  Standard statements (:data:`STANDARD_PROPERTIES`)
    are left out; those on existing items are counted, so the page never
    says "nothing" when only they were added.

    Returns:
        ``(statements by QID of a created item, relations, number of standard statements on existing items)``.
    '''
    by_item = defaultdict(list)
    relations = []
    standard_added = 0
    for stmt in job.get("statements", []):
        subj, subj_qid, prop, obj, obj_qid = stmt[0], stmt[1], stmt[2], stmt[3], stmt[4]
        qualifiers  = stmt[5] if len(stmt) > 5 else []
        unit_label  = stmt[6] if len(stmt) > 6 else ''
        unit_qid    = stmt[7] if len(stmt) > 7 else ''
        # True: the statement was on the portal already, only qualifiers were added
        qualifiers_added = stmt[8] if len(stmt) > 8 else False
        obj_url = object_url(prop, obj, obj_qid)
        for q in qualifiers:
            q['obj_url'] = object_url(q['prop'], q['obj'], q.get('obj_qid', ''))
        if prop in STANDARD_PROPERTIES:
            if subj_qid not in created_qids:
                standard_added += 1
            continue
        if subj_qid in created_qids:
            by_item[subj_qid].append(
                {'prop': prop, 'obj': obj, 'obj_qid': obj_qid, 'obj_url': obj_url,
                 'qualifiers': qualifiers, 'unit_label': unit_label, 'unit_qid': unit_qid}
            )
        else:
            relations.append({
                'subject': subj, 'subject_qid': subj_qid,
                'prop': prop, 'obj': obj, 'obj_qid': obj_qid, 'obj_url': obj_url,
                'qualifiers': qualifiers, 'unit_label': unit_label, 'unit_qid': unit_qid,
                'qualifiers_added': qualifiers_added,
            })
    return by_item, relations, standard_added


def group_by_class(ids, by_item):
    '''The created items *ids* with their statements, grouped by class in :data:`CLASS_ORDER`.

    Returns:
        ``[(class, [{name, qid, stmts}, …]), …]``.
    '''
    items_by_class = defaultdict(list)
    for cls, name, qid in ids:
        items_by_class[cls].append({'name': name, 'qid': qid, 'stmts': by_item.get(qid, [])})
    return [
        (cls, items_by_class[cls]) for cls in CLASS_ORDER if cls in items_by_class
    ] + [
        (cls, items) for cls, items in items_by_class.items() if cls not in CLASS_ORDER
    ]


def result_graph(groups, relations, item_url):
    '''The graph of the result page for Cytoscape: ``{'nodes': […], 'edges': […]}``.

    Created items are ``'new'`` nodes, other portal items ``'item'`` nodes
    (a node once ``'new'`` stays so), values without item ``'literal'``
    nodes; every statement is an edge from its item to its value, and a
    quantity value with a unit has an edge to its unit.

    Args:
        groups:    The created items by class (:func:`group_by_class`).
        relations: The statements added to existing items (:func:`split_statements`).
        item_url:  The URL of the portal's items (the QID is appended).
    '''
    nodes, edges = {}, []
    literals = 0

    def add_item(qid, label, node_type, cls=''):
        if not qid:
            return
        existing = nodes.get(qid)
        # 'new' always wins; only insert 'item' if the node isn't already known
        if existing is None or (node_type == 'new' and existing['node_type'] != 'new'):
            nodes[qid] = {'id': qid, 'label': label, 'node_type': node_type, 'cls': cls, 'url': item_url + qid}

    def add_statement(source, statement):
        nonlocal literals
        if statement['obj_qid']:
            add_item(statement['obj_qid'], statement['obj'], 'item')
            target = statement['obj_qid']
        else:
            target = f'_lit_{literals}'
            literals += 1
            nodes[target] = {'id': target, 'label': statement['obj'], 'node_type': 'literal', 'cls': '',
                             'url': statement.get('obj_url', '')}
        edges.append({'source': source, 'target': target,
                      'label': statement['prop'], 'qualifiers': statement.get('qualifiers', [])})
        if statement.get('unit_qid'):
            add_item(statement['unit_qid'], statement['unit_label'], 'item')
            edges.append({'source': target, 'target': statement['unit_qid'], 'label': 'unit', 'qualifiers': []})

    for cls, items in groups:
        for item in items:
            add_item(item['qid'], item['name'], 'new', cls)
            for statement in item['stmts']:
                add_statement(item['qid'], statement)
    for relation in relations:
        if relation['subject_qid']:
            add_item(relation['subject_qid'], relation['subject'], 'item')
            add_statement(relation['subject_qid'], relation)
    return {'nodes': list(nodes.values()), 'edges': edges}
