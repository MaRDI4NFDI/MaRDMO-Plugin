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

from dataclasses import dataclass

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
    '''Return the QID of a selected portal item (``"mardi:Q42"`` → ``"Q42"``), or ``None``.

    Only items of the MaRDI Portal: the QID of a Wikidata item (``"wikidata:Q42"``)
    names another item on the portal, and an own item has none.
    '''
    source, _, qid = str(item.get('ID', '')).partition(':')
    return qid if source == 'mardi' and _QID_RE.match(qid) else None


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


ITEM, KEYWORD, PROPERTY = 'item', 'keyword', 'property'
'''The kinds of filters: a portal item, a keyword, a model property (an option).'''


@dataclass(frozen=True)
class Mode:
    '''A search mode of the search catalog.

    Attributes:
        option:  Key of the mode's option in the options (``answers['search']['options']``).
        name:    The mode in the message without filters (``"Model search requested …"``).
        query:   The base query; ``{}`` takes the filters' parts.
        filters: ``(answer key, label in the query's comment, query part, kind)`` per filter.
    '''
    option: str
    name: str
    query: str
    filters: tuple


MODES = (
    Mode('InterdisciplinaryWorkflow', 'Workflow', QUERY_BASE_WORKFLOW_SEARCH, (
        ('research-objective', 'research objective', WF_RESEARCH_OBJ_SPARQL, KEYWORD),
        ('academic-discipline', 'academic discipline', WF_DISCIPLINE_SPARQL, ITEM),
        ('mathematical-model', 'mathematical model', WF_MODEL_SPARQL, ITEM),
        ('algorithm', 'algorithm', WF_ALGORITHM_SPARQL, ITEM),
        ('software', 'software', WF_SOFTWARE_SPARQL, ITEM),
        ('hardware', 'hardware', WF_HARDWARE_SPARQL, ITEM),
        ('method', 'method', WF_METHOD_SPARQL, ITEM),
        ('instrument', 'instrument', WF_INSTRUMENT_SPARQL, ITEM),
        ('data-set', 'data set', WF_DATASET_SPARQL, ITEM),
    )),
    Mode('MathematicalModel', 'Model', QUERY_BASE_MODEL_SEARCH, (
        ('mathematical-model-properties', 'model property', MM_PROPERTY_SPARQL, PROPERTY),
        ('research-problem', 'research problem', MM_PROBLEM_SPARQL, ITEM),
        ('academic-discipline', 'academic discipline', MM_DISCIPLINE_SPARQL, ITEM),
        ('computational-task', 'computational task', MM_TASK_SPARQL, ITEM),
        ('formula', 'formula', MM_FORMULA_SPARQL, ITEM),
        ('quantity', 'quantity', MM_QUANTITY_SPARQL, ITEM),
    )),
    Mode('Algorithm', 'Algorithm', QUERY_BASE_ALGORITHM_SEARCH, (
        ('algorithmic-task', 'algorithmic task', ALG_TASK_SPARQL, ITEM),
        ('software', 'software', ALG_SOFTWARE_SPARQL, ITEM),
    )),
)
'''The search modes, in the order they are checked.'''


def _parts(selected, mode, items, props):
    '''The query parts of the filters of *mode* the user *selected*, each with a comment line.

    Selections without use (an item not on the MaRDI Portal, an empty
    keyword, an unknown property) are left out.
    '''
    parts = []
    for key, label, template, kind in mode.filters:
        for idx, value in enumerate(selected.get(key, {}).values()):
            if kind == KEYWORD:
                if value:
                    parts.append(
                        f"  # {label}: {_comment(value)}\n"
                        + template.format(idx=idx, keyword=sparql_string(value.lower()), **items, **props)
                    )
            elif kind == PROPERTY:
                uri_tail = value.rsplit('/', 1)[-1]
                item_key = MM_PROPERTY_TO_ITEM.get(uri_tail)
                if item_key:
                    parts.append(
                        f"  # {label}: {uri_tail.replace('-', ' ')}\n"
                        + template.format(qid=items[item_key], **items, **props)
                    )
            else:
                qid = _item_qid(value)
                if qid:
                    parts.append(
                        f"  # {label}: {_comment(value.get('Name'))}\n"
                        + template.format(idx=idx, qid=qid, **items, **props)
                    )
    return parts


def search(answers, options):
    '''Build the SPARQL query from the user's search criteria, run it, and store the results.

    The search mode (``answers["search"]["options"]``) is one of
    :data:`MODES`; its filters the user selected make the query, which runs
    on the MaRDI Portal.  The escaped query, the result count and the links
    are written back into *answers*.

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

    mode = next((mode for mode in MODES if answers['search'].get('options') == options[mode.option]), None)
    if mode is None:
        return answers

    selected = answers['search']
    if not any(selected.get(key) for key, _, _, _ in mode.filters):
        answers['query'] = f'{mode.name} search requested but no parameters defined.'
        answers['no_results'] = '0'
        answers['links'] = []
        return answers

    items = get_items()
    props = get_properties()
    parts = _parts(selected, mode, items, props)
    if not parts:
        # Only unusable selections (no valid QID): same as no parameters
        answers['query'] = 'Search requested but no usable parameters defined.'
        return answers

    query = "\n".join(
        line
        for line in mode.query.format(
            "\n".join(parts),
            **items,
            **props,
        ).splitlines()
        if line.strip()
    )

    _run_query(answers, query)
    return answers
