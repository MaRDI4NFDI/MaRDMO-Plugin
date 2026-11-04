# Split MaRDI Portal Queries

The MaRDI Portal queries for models, formulations, tasks and quantities (and their basics
variants) exist only as parts: `model_mardi_1.sparql`, `model_mardi_2.sparql`, … A query with
all OPTIONAL blocks at once takes the portal several times longer than its parts together,
because the cost grows faster than the number of blocks and blocks with several values each
multiply each other's rows before they are grouped.

The handlers still name the query by its path, e.g. `model/queries/model_mardi.sparql`;
`get_sparql_query_parts()` finds the parts by number, `query_sparql_parts()` runs them one after
another and merges their rows into rows shaped like those of a single query, so the parsing in
`model/models.py` is the same for both. The Wikidata queries are not split.

## Rules

- **Part 1 decides which items exist.** It holds the required patterns (e.g. the class UNION of
  the quantity query) and single values that are not yes/no flags (e.g. QUDT IDs), selects
  `?qid`, and groups by `?id` plus its non-aggregated columns. Items it does not return are not
  filled, and if it returns nothing, the other parts are not run.
- **Every further part returns one row per item.** It selects `?id`, its yes/no flags
  (`BIND(COALESCE(...))`) and its list columns (`GROUP_CONCAT`), and groups by `?id` plus the flags.
- **About four OPTIONAL blocks per part.** More blocks make a part slower again; fewer only add
  requests.
- **Every column comes from exactly one part.** Variables are not shared between parts.
- **Never group by a list variable.** A `GROUP BY ?descriptionLong` splits an item into one row
  per value, and MaRDMO then keeps only one of them.
- If any part fails, no item of the batch is filled.

## Adding or Changing a Column

- **Yes/no flag or list:** add the `OPTIONAL` block (and its `BIND`) to a part with fewer than
  four blocks, or to a new part with the next number; add the column to that part's `SELECT`,
  and a flag also to its `GROUP BY`.
- **New part:** copy the head of an existing further part (the `VALUES ?id {{{0}}}` line and
  `GROUP BY ?id`); it is picked up by its number, no code changes are needed.
- Update the table below.

## Parts

### `model_mardi_*.sparql` (9 parts)

| Part | Columns |
|---|---|
| 1 | `qid` |
| 2 | `is_linear`, `is_not_linear`, `description_long`, `aliases` |
| 3 | `is_dynamic`, `is_static`, `is_deterministic`, `is_stochastic` |
| 4 | `is_dimensionless`, `is_dimensional`, `is_space_continuous`, `is_space_discrete` |
| 5 | `is_time_continuous`, `is_time_discrete`, `models`, `assumes` |
| 6 | `contains_formulation`, `used_by`, `specialized_by`, `specializes` |
| 7 | `approximated_by`, `approximates`, `contains_model`, `contained_in_model` |
| 8 | `discretized_by`, `discretizes`, `linearized_by`, `linearizes` |
| 9 | `has_weak_formulation`, `is_weak_formulation_of`, `similar_to`, `publication` |

### `model-basics_mardi_*.sparql` (9 parts)

| Part | Columns |
|---|---|
| 1 | `qid` |
| 2 | `is_linear`, `is_not_linear`, `is_dynamic`, `is_static` |
| 3 | `is_deterministic`, `is_stochastic`, `is_dimensionless`, `is_dimensional` |
| 4 | `is_space_continuous`, `is_space_discrete`, `is_time_continuous`, `is_time_discrete` |
| 5 | `models`, `assumes`, `used_by`, `contains_formulation` |
| 6 | `specialized_by`, `specializes`, `approximated_by`, `approximates` |
| 7 | `contains_model`, `contained_in_model`, `discretized_by`, `discretizes` |
| 8 | `linearized_by`, `linearizes`, `has_weak_formulation`, `is_weak_formulation_of` |
| 9 | `similar_to`, `publication` |

### `formulation_mardi_*.sparql` (10 parts)

| Part | Columns |
|---|---|
| 1 | `qid` |
| 2 | `is_ordinary_differential_equation`, `is_partial_differential_equation`, `description_long`, `aliases` |
| 3 | `is_linear`, `is_not_linear`, `is_stochastic_differential_equation`, `is_integro_differential_equation` |
| 4 | `is_dynamic`, `is_static`, `is_deterministic`, `is_stochastic` |
| 5 | `is_dimensionless`, `is_dimensional`, `is_space_continuous`, `is_space_discrete` |
| 6 | `is_time_continuous`, `is_time_discrete`, `assumes`, `contains_formulation` |
| 7 | `specialized_by`, `specializes`, `approximated_by`, `approximates` |
| 8 | `nondimensionalized_by`, `nondimensionalizes`, `discretized_by`, `discretizes` |
| 9 | `linearized_by`, `linearizes`, `has_weak_formulation`, `is_weak_formulation_of` |
| 10 | `similar_to`, `publication` |

### `formulation-basics_mardi_*.sparql` (9 parts)

| Part | Columns |
|---|---|
| 1 | `qid`, `reference` |
| 2 | `is_ordinary_differential_equation`, `is_partial_differential_equation`, `is_stochastic_differential_equation`, `is_integro_differential_equation` |
| 3 | `is_linear`, `is_not_linear`, `is_dynamic`, `is_static` |
| 4 | `is_deterministic`, `is_stochastic`, `is_dimensionless`, `is_dimensional` |
| 5 | `is_time_continuous`, `is_time_discrete`, `is_space_continuous`, `is_space_discrete` |
| 6 | `specialized_by`, `specializes`, `approximated_by`, `approximates` |
| 7 | `nondimensionalized_by`, `nondimensionalizes`, `discretized_by`, `discretizes` |
| 8 | `linearized_by`, `linearizes`, `has_weak_formulation`, `is_weak_formulation_of` |
| 9 | `similar_to`, `publication` |

### `task_mardi_*.sparql` (7 parts)

| Part | Columns |
|---|---|
| 1 | `qid` |
| 2 | `is_linear`, `is_not_linear`, `aliases`, `description_long` |
| 3 | `is_space_continuous`, `is_space_discrete`, `is_time_continuous`, `is_time_discrete` |
| 4 | `assumes`, `contains_formulation`, `contains_quantity`, `specialized_by` |
| 5 | `specializes`, `approximated_by`, `approximates`, `contains_task` |
| 6 | `contained_in_task`, `discretized_by`, `discretizes`, `linearized_by` |
| 7 | `linearizes`, `similar_to`, `publication` |

### `task-basics_mardi_*.sparql` (6 parts)

| Part | Columns |
|---|---|
| 1 | `qid` |
| 2 | `is_linear`, `is_not_linear`, `is_space_continuous`, `is_space_discrete` |
| 3 | `is_time_continuous`, `is_time_discrete`, `contains_formulation`, `specialized_by` |
| 4 | `specializes`, `approximated_by`, `approximates`, `contains_task` |
| 5 | `contained_in_task`, `discretized_by`, `discretizes`, `linearized_by` |
| 6 | `linearizes`, `similar_to`, `publication` |

### `quantity_mardi_*.sparql` (8 parts)

| Part | Columns |
|---|---|
| 1 | `qid`, `class`, `qudt_quantitykind_id`, `qudt_constant_id` |
| 2 | `is_dynamic`, `is_static`, `aliases`, `description_long` |
| 3 | `is_deterministic`, `is_stochastic`, `is_dimensionless`, `is_dimensional` |
| 4 | `is_space_continuous`, `is_space_discrete`, `is_time_continuous`, `is_time_discrete` |
| 5 | `is_chemical_constant`, `is_mathematical_constant`, `is_physical_constant`, `specialized_by` |
| 6 | `specializes`, `approximated_by`, `discretizes`, `discretized_by` |
| 7 | `approximates`, `linearized_by`, `linearizes`, `nondimensionalized_by` |
| 8 | `nondimensionalizes`, `similar_to`, `publication` |
