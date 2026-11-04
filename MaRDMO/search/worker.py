'''Background worker for the cross-catalog MaRDI search questionnaire.

Dispatches on the selected search mode and builds a SPARQL query from the
user-supplied filter criteria, executes it against the MaRDI Portal, and
stores the results for the view layer to render.

Three search modes are supported:

- **InterdisciplinaryWorkflow** — filters: research objective, academic
  discipline, mathematical model, algorithm, software, hardware, method,
  instrument, data set.
- **MathematicalModel** — filters: model properties, research problem,
  academic discipline, computational task, formula, quantity.
- **Algorithm** — filters: algorithmic task, software.

Provides:

- ``search`` — entry point called by the view layer; mutates *answers* in
  place with ``"query"``, ``"no_results"``, and ``"links"`` keys.
'''

import html
import re

from ..getters import get_item_url, get_items, get_properties, get_url
from ..queries import query_sparql, sparql_string
from .sparql import (
    QUERY_BASE_WORKFLOW_SEARCH,
    WF_RESEARCH_OBJ_SPARQL,
    WF_DISCIPLINE_SPARQL,
    WF_MODEL_SPARQL,
    WF_ALGORITHM_SPARQL,
    WF_SOFTWARE_SPARQL,
    WF_HARDWARE_SPARQL,
    WF_METHOD_SPARQL,
    WF_INSTRUMENT_SPARQL,
    WF_DATASET_SPARQL,
    QUERY_BASE_MODEL_SEARCH,
    MM_PROPERTY_TO_ITEM,
    MM_PROPERTY_SPARQL,
    MM_PROBLEM_SPARQL,
    MM_DISCIPLINE_SPARQL,
    MM_TASK_SPARQL,
    MM_FORMULA_SPARQL,
    MM_QUANTITY_SPARQL,
    QUERY_BASE_ALGORITHM_SEARCH,
    ALG_TASK_SPARQL,
    ALG_SOFTWARE_SPARQL,
)

_QID_RE = re.compile(r'^Q\d+$')

def _comment(text):
    '''Return *text* on a single line, for use in a SPARQL comment.'''
    return ' '.join(str(text or '').split())


def _item_qid(item):
    '''Return the QID of a selected portal item (``"mardi:Q42"`` → ``"Q42"``), or ``None``.'''
    qid = str(item.get('ID', '')).split(':')[-1]
    return qid if _QID_RE.match(qid) else None


def _run_query(answers, query):
    '''Run *query* on the MaRDI Portal and store query, result count, and links in *answers*.

    A failed query (portal unreachable, query rejected) sets
    ``answers["search_failed"]`` instead of reporting zero results.
    '''
    answers['query'] = html.escape(query).replace('\n', '<br>')
    results = query_sparql(query, get_url('mardi', 'sparql'), strict=True)
    if results is None:
        answers['search_failed'] = True
        answers['no_results'] = '0'
        answers['links'] = []
        return
    answers['no_results'] = str(len(results))
    answers['links'] = [
        [result["label"]["value"], f"{get_item_url('mardi')}{result['qid']['value']}"]
        for result in results
    ]


def search(answers, options):
    '''Build SPARQL queries from user search criteria, execute them, and store results.

    Dispatches on ``answers["search"]["options"]`` to one of three search
    modes: Interdisciplinary Workflow, Mathematical Model, or Algorithm.
    For each mode, constructs a SPARQL query from the selected filter criteria,
    executes it against the appropriate endpoint (MaRDI Portal or MathAlgoDB),
    and writes the escaped query string, result count, and link list back into
    *answers*.

    Args:
        answers: Top-level answers dict (mutated in place with ``"query"``,
                 ``"no_results"``, and ``"links"`` keys).
        options: Global RDMO options dict used for option-value comparisons.

    Returns:
        The mutated *answers* dict.
    '''
    answers.setdefault('query', '')
    answers.setdefault('no_results', '0')
    answers.setdefault('links', [])
    answers.setdefault('search_failed', False)

    if answers['search'].get('options') == options['InterdisciplinaryWorkflow']:

        s = answers['search']
        items = get_items()
        props = get_properties()

        filter_keys = [
            'research-objective', 'academic-discipline', 'mathematical-model',
            'algorithm', 'software', 'hardware', 'method', 'instrument', 'data-set',
        ]
        if not any(s.get(k) for k in filter_keys):
            answers['query'] = 'Workflow search requested but no parameters defined.'
            answers['no_results'] = '0'
            answers['links'] = []
            return answers

        parts = []

        for idx, keyword in enumerate(s.get('research-objective', {}).values()):
            if keyword:
                parts.append(
                    f"  # research objective: {_comment(keyword)}\n"
                    + WF_RESEARCH_OBJ_SPARQL.format(
                        idx=idx, keyword=sparql_string(keyword.lower()), **items, **props
                    )
                )

        for idx, item in enumerate(s.get('academic-discipline', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # academic discipline: {_comment(item.get('Name'))}\n"
                + WF_DISCIPLINE_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('mathematical-model', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # mathematical model: {_comment(item.get('Name'))}\n"
                + WF_MODEL_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('algorithm', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # algorithm: {_comment(item.get('Name'))}\n"
                + WF_ALGORITHM_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('software', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # software: {_comment(item.get('Name'))}\n"
                + WF_SOFTWARE_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('hardware', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # hardware: {_comment(item.get('Name'))}\n"
                + WF_HARDWARE_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('method', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # method: {_comment(item.get('Name'))}\n"
                + WF_METHOD_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('instrument', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # instrument: {_comment(item.get('Name'))}\n"
                + WF_INSTRUMENT_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('data-set', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # data set: {_comment(item.get('Name'))}\n"
                + WF_DATASET_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        if not parts:
            # Only unusable selections (no valid QID): same as no parameters
            answers['query'] = 'Search requested but no usable parameters defined.'
            return answers

        query = "\n".join(
            line
            for line in QUERY_BASE_WORKFLOW_SEARCH.format(
                "\n".join(parts),
                **items,
                **props,
            ).splitlines()
            if line.strip()
        )

        _run_query(answers, query)

    elif answers['search'].get('options') == options['MathematicalModel']:

        s = answers['search']
        items = get_items()
        props = get_properties()

        filter_keys = [
            'mathematical-model-properties', 'research-problem',
            'academic-discipline', 'computational-task', 'formula', 'quantity',
        ]
        if not any(s.get(k) for k in filter_keys):
            answers['query'] = 'Model search requested but no parameters defined.'
            answers['no_results'] = '0'
            answers['links'] = []
            return answers

        parts = []

        for option_uri in s.get('mathematical-model-properties', {}).values():
            uri_tail = option_uri.rsplit('/', 1)[-1]
            item_key = MM_PROPERTY_TO_ITEM.get(uri_tail)
            if item_key:
                label = uri_tail.replace('-', ' ')
                parts.append(
                    f"  # model property: {label}\n"
                    + MM_PROPERTY_SPARQL.format(
                        qid=items[item_key], **items, **props
                    )
                )

        for idx, item in enumerate(s.get('research-problem', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # research problem: {_comment(item.get('Name'))}\n"
                + MM_PROBLEM_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('academic-discipline', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # academic discipline: {_comment(item.get('Name'))}\n"
                + MM_DISCIPLINE_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('computational-task', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # computational task: {_comment(item.get('Name'))}\n"
                + MM_TASK_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('formula', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # formula: {_comment(item.get('Name'))}\n"
                + MM_FORMULA_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('quantity', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # quantity: {_comment(item.get('Name'))}\n"
                + MM_QUANTITY_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        if not parts:
            # Only unusable selections (no valid QID): same as no parameters
            answers['query'] = 'Search requested but no usable parameters defined.'
            return answers

        query = "\n".join(
            line
            for line in QUERY_BASE_MODEL_SEARCH.format(
                "\n".join(parts),
                **items,
                **props,
            ).splitlines()
            if line.strip()
        )

        _run_query(answers, query)

    elif answers['search'].get('options') == options['Algorithm']:

        s = answers['search']
        items = get_items()
        props = get_properties()

        filter_keys = ['algorithmic-task', 'software']
        if not any(s.get(k) for k in filter_keys):
            answers['query'] = (
                'Algorithm search requested but no parameters defined.'
            )
            answers['no_results'] = '0'
            answers['links'] = []
            return answers

        parts = []

        for idx, item in enumerate(s.get('algorithmic-task', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # algorithmic task: {_comment(item.get('Name'))}\n"
                + ALG_TASK_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        for idx, item in enumerate(s.get('software', {}).values()):
            qid = _item_qid(item)
            if not qid:
                continue
            parts.append(
                f"  # software: {_comment(item.get('Name'))}\n"
                + ALG_SOFTWARE_SPARQL.format(idx=idx, qid=qid, **items, **props)
            )

        if not parts:
            # Only unusable selections (no valid QID): same as no parameters
            answers['query'] = 'Search requested but no usable parameters defined.'
            return answers

        query = "\n".join(
            line
            for line in QUERY_BASE_ALGORITHM_SEARCH.format(
                "\n".join(parts),
                **items,
                **props,
            ).splitlines()
            if line.strip()
        )

        _run_query(answers, query)

    return answers
