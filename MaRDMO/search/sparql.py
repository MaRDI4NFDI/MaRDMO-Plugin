'''SPARQL query templates and filter fragments used by the MaRDMO portal search.

Each ``QUERY_BASE_*`` string is a parameterised SPARQL SELECT template that is
assembled at runtime by inserting placeholder fragments (``*_SPARQL``).  The
placeholder strings bind Wikibase item/property QIDs at format-time via
:meth:`str.format`.
'''


# ---------------------------------------------------------------------------
# Workflow search — base query and per-entity-type fragment templates.
# Each fragment uses {idx} and {qid} for runtime values and {property_name}
# for Wikibase QIDs; all are substituted in one .format() call.
# ---------------------------------------------------------------------------

QUERY_BASE_WORKFLOW_SEARCH = """SELECT DISTINCT ?label ?qid
WHERE {{
  ?workflow wdt:{instance of} wd:{research workflow} ;
            rdfs:label ?label .
  FILTER(LANG(?label) = "en")
{0}
  BIND(STRAFTER(STR(?workflow), STR(wd:)) AS ?qid)
}}
LIMIT 10"""

WF_RESEARCH_OBJ_SPARQL = (
    "  ?workflow wdt:{problem statement} ?obj_{idx} .\n"
    "  FILTER(CONTAINS(lcase(str(?obj_{idx})), {keyword}))\n"  # keyword: escaped literal
)

WF_DISCIPLINE_SPARQL = (
    "  ?workflow wdt:{contains} ?discipline_step_{idx} .\n"
    "  ?discipline_step_{idx} wdt:{instance of} wd:{process step} .\n"
    "  ?discipline_step_{idx} wdt:{field of work} wd:{qid} .\n"
)

WF_MODEL_SPARQL = (
    "  ?workflow p:{uses} ?model_statement_{idx} .\n"
    "  ?model_statement_{idx} ps:{uses} wd:{qid} .\n"
)

WF_ALGORITHM_SPARQL = (
    "  ?workflow wdt:{contains} ?algorithm_step_{idx} .\n"
    "  ?algorithm_step_{idx} wdt:{instance of} wd:{process step} .\n"
    "  ?algorithm_step_{idx} p:{uses} ?algorithm_statement_{idx} .\n"
    "  ?algorithm_statement_{idx} ps:{uses} wd:{qid} .\n"
    "  wd:{qid} wdt:{instance of} wd:{algorithm} .\n"
)

WF_SOFTWARE_SPARQL = (
    "  ?workflow wdt:{contains} ?software_step_{idx} .\n"
    "  ?software_step_{idx} wdt:{instance of} wd:{process step} .\n"
    "  ?software_step_{idx} p:{uses} ?software_statement_{idx} .\n"
    "  ?software_statement_{idx} ps:{uses} ?software_algorithm_{idx} .\n"
    "  ?software_algorithm_{idx} wdt:{instance of} wd:{algorithm} .\n"
    "  ?software_statement_{idx} pq:{platform} wd:{qid} .\n"
    "  wd:{qid} wdt:{instance of} wd:{software} .\n"
)

WF_HARDWARE_SPARQL = (
    "  ?workflow wdt:{contains} ?hardware_step_{idx} .\n"
    "  ?hardware_step_{idx} wdt:{instance of} wd:{process step} .\n"
    "  ?hardware_step_{idx} p:{uses} ?hardware_statement_{idx} .\n"
    "  ?hardware_statement_{idx} pq:{platform} wd:{qid} .\n"
    "  wd:{qid} wdt:{instance of} wd:{computer hardware} .\n"
)

WF_METHOD_SPARQL = (
    "  ?workflow wdt:{contains} ?method_step_{idx} .\n"
    "  ?method_step_{idx} wdt:{instance of} wd:{process step} .\n"
    "  ?method_step_{idx} p:{uses} ?method_statement_{idx} .\n"
    "  ?method_statement_{idx} ps:{uses} wd:{qid} .\n"
    "  wd:{qid} wdt:{instance of} wd:{method} .\n"
)

WF_INSTRUMENT_SPARQL = (
    "  ?workflow wdt:{contains} ?instrument_step_{idx} .\n"
    "  ?instrument_step_{idx} wdt:{instance of} wd:{process step} .\n"
    "  ?instrument_step_{idx} p:{uses} ?instrument_statement_{idx} .\n"
    "  ?instrument_statement_{idx} ps:{uses} ?instrument_method_{idx} .\n"
    "  ?instrument_method_{idx} wdt:{instance of} wd:{method} .\n"
    "  ?instrument_statement_{idx} pq:{platform} wd:{qid} .\n"
    "  wd:{qid} wdt:{instance of} wd:{research tool} .\n"
)

WF_DATASET_SPARQL = (
    "  {{\n"
    "    ?workflow wdt:{contains} ?dataset_step_{idx}a .\n"
    "    ?dataset_step_{idx}a wdt:{instance of} wd:{process step} .\n"
    "    ?dataset_step_{idx}a wdt:{input data set} wd:{qid} .\n"
    "  }}\n"
    "  UNION\n"
    "  {{\n"
    "    ?workflow wdt:{contains} ?dataset_step_{idx}b .\n"
    "    ?dataset_step_{idx}b wdt:{instance of} wd:{process step} .\n"
    "    ?dataset_step_{idx}b wdt:{output data set} wd:{qid} .\n"
    "  }}\n"
)

# ---------------------------------------------------------------------------
# Model search — base query and per-criterion fragment templates.
# ---------------------------------------------------------------------------

QUERY_BASE_MODEL_SEARCH = """SELECT DISTINCT ?label ?qid
WHERE {{
  ?model wdt:{instance of} wd:{mathematical model} ;
         rdfs:label ?label .
  FILTER(LANG(?label) = "en")
{0}
  BIND(STRAFTER(STR(?model), STR(wd:)) AS ?qid)
}}
LIMIT 10"""

MM_PROPERTY_TO_ITEM = {
    'is-deterministic':    'deterministic model',
    'is-stochastic':       'probabilistic model',
    'is-dimensional':      'dimensional model',
    'is-dimensionless':    'dimensionless model',
    'is-dynamic':          'dynamic model',
    'is-static':           'static model',
    'is-linear':           'linear model',
    'is-not-linear':       'nonlinear model',
    'is-space-continuous': 'continuous-space model',
    'is-space-discrete':   'discrete-space model',
    'is-time-continuous':  'continuous-time model',
    'is-time-discrete':    'discrete-time model',
}

MM_PROPERTY_SPARQL = "  ?model wdt:{instance of} wd:{qid} .\n"

MM_PROBLEM_SPARQL = "  wd:{qid} wdt:{modelled by} ?model .\n"

MM_DISCIPLINE_SPARQL = (
    "  ?discipline_problem_{idx} wdt:{modelled by} ?model .\n"
    "  wd:{qid} wdt:{contains} ?discipline_problem_{idx} .\n"
)

MM_TASK_SPARQL = (
    "  ?model wdt:{used by} wd:{qid} .\n"
    "  wd:{qid} wdt:{instance of} wd:{computational task} .\n"
)

MM_FORMULA_SPARQL = (
    "  {{\n"
    "    ?model p:{assumes} ?formula_assumes_statement_{idx} .\n"
    "    ?formula_assumes_statement_{idx} ps:{assumes} wd:{qid} .\n"
    "  }}\n"
    "  UNION\n"
    "  {{\n"
    "    ?model p:{contains} ?formula_contains_statement_{idx} .\n"
    "    ?formula_contains_statement_{idx} ps:{contains} wd:{qid} .\n"
    "  }}\n"
)

MM_QUANTITY_SPARQL = (
    "  {{\n"
    "    ?model wdt:{used by} ?quantity_task_{idx} .\n"
    "    ?quantity_task_{idx} wdt:{contains} wd:{qid} .\n"
    "  }}\n"
    "  UNION\n"
    "  {{\n"
    "    ?model p:{assumes} ?quantity_assumes_statement_{idx} .\n"
    "    ?quantity_assumes_statement_{idx} ps:{assumes} ?quantity_formula_{idx} .\n"
    "    ?quantity_formula_{idx} p:{in defining formula} ?quantity_symbol_{idx} .\n"
    "    ?quantity_symbol_{idx} pq:{symbol represents} wd:{qid} .\n"
    "  }}\n"
    "  UNION\n"
    "  {{\n"
    "    ?model p:{contains} ?quantity_contains_statement_{idx} .\n"
    "    ?quantity_contains_statement_{idx} ps:{contains} ?quantity_formula2_{idx} .\n"
    "    ?quantity_formula2_{idx} p:{in defining formula} ?quantity_symbol2_{idx} .\n"
    "    ?quantity_symbol2_{idx} pq:{symbol represents} wd:{qid} .\n"
    "  }}\n"
)

# ---------------------------------------------------------------------------
# Algorithm search — base query and per-criterion fragment templates.
# ---------------------------------------------------------------------------

QUERY_BASE_ALGORITHM_SEARCH = """SELECT DISTINCT ?label ?qid
WHERE {{
  ?algo wdt:{instance of} wd:{algorithm} ;
        rdfs:label ?label .
  FILTER(LANG(?label) = "en")
{0}
  BIND(STRAFTER(STR(?algo), STR(wd:)) AS ?qid)
}}
LIMIT 10"""

ALG_TASK_SPARQL = "  wd:{qid} wdt:{solved by} ?algo .\n"

ALG_SOFTWARE_SPARQL = "  ?algo wdt:{implemented by} wd:{qid} .\n"
