# How to Add a Data Property

A *data property* is a boolean characteristic of a MathModDB entity — for
example *is dimensional* or *is physical constant*.  When a user selects such
a property in the RDMO interview, MaRDMO validates the selection, writes it to
the questionnaire, checks it before export, and maps it to a Wikibase statement
on the MaRDI Portal.

Properties come in two flavours:

- **Class-dependent** — the corresponding MaRDI Portal item has a different
  name per entity class.  Example: *is dimensional* maps to "dimensional model",
  "dimensional formula", "dimensional quantity", "dimensional quantity kind" —
  separate Wikibase items for each class.
- **Class-independent** — one Wikibase item is used regardless of entity class.
  Example: *is physical constant* maps to "physical constant" for every entity
  class that supports it.

The two walkthroughs below use these properties as concrete examples.  Both
properties are part of the MaRDMO Catalogs for detailed and basic documentation
of mathematical models.

!!! note "Quantity and Quantity Kind"
    The entity classes *Quantity* and *Quantity Kind* are treated together in
    the backend under the key `quantity`.  They share one MaRDI Portal query
    (the parts `split/quantity_mardi_*.sparql`) and one Wikidata query
    (`quantity_wikidata.sparql`), where both item types are covered via a UNION
    pattern.

---

## Case 1 — Class-Dependent: is dimensional

### Step 1a — Add the Option to RDMO

Create a new option with the URI
`https://rdmo.mardi4nfdi.de/terms/options/mathmoddb/is-dimensional` and add it
to each relevant optionset in RDMO.  For *is dimensional* the relevant
optionsets are:

- `https://rdmo.mardi4nfdi.de/terms/options/model-properties`
- `https://rdmo.mardi4nfdi.de/terms/options/formulation-properties`
- `https://rdmo.mardi4nfdi.de/terms/options/quantity-properties`

See [How to Create a New Option](../rdmo/add-option.md)
and [How to Create a New Optionset](../rdmo/add-optionset.md)
for further information.

### Step 1b — Register the Option in `model/data/mapping.json`

Add an entry to `model/data/mapping.json`.  This file maps MathModDB property
keys to their RDMO option URIs and human-readable labels:

```json
{"key": "is_dimensional", "url": "https://rdmo.mardi4nfdi.de/terms/options/mathmoddb/is-dimensional", "label": "is dimensional"}
```

### Step 2 — Register MaRDI Portal QIDs

Add one entry per entity class to `data/items.json` (productive portal) and
`data/items_staging.json` (staging portal, for testing purposes):

**data/items.json:**

```json
"dimensional model":         "Q6775551",
"dimensional formula":       "Q6775550",
"dimensional quantity":      "Q6775552",
"dimensional quantity kind": "Q6775553"
```

**data/items_staging.json:**

```json
"dimensional model":         "Q13324",
"dimensional formula":       "Q13323",
"dimensional quantity":      "Q13325",
"dimensional quantity kind": "Q13326"
```

### Step 3 — `model/constants.py`

**3a** — Mutual exclusion pair (*is dimensional* and *is dimensionless* cannot
both be true at the same time):

```python
data_properties_check = [
    ...
    ('is_dimensionless', 'is_dimensional'),
]
```

**3b** — Entity classes that carry this property (model, formula, quantity,
quantity kind):

```python
data_properties_per_class = {
    'model':       [..., 'is_dimensional'],
    'formulation': [..., 'is_dimensional'],
    'quantity':    [..., 'is_dimensional'],
}
```

**3c** — Register as class-dependent.  The second element is the item name
prefix; MaRDMO appends the entity class name automatically to look up the
correct Wikibase item ("dimensional model", "dimensional formula", etc.):

```python
DEPENDENT_PROPERTIES = [
    ...
    ('is_dimensional', 'dimensional'),
]
```

### Step 4 — SPARQL Queries

For each entity class the property applies to, edit the corresponding queries in
`model/queries/` — both the MaRDI and Wikidata variants, and both the full
and `-basics` variants where they exist.  The MaRDI queries of these classes
exist only as parts in `model/queries/split/`; its `README.md` lists which part
requests which column.

Affected files for *is dimensional*:

| Entity class | Files |
|---|---|
| Model | `split/model_mardi_*.sparql`, `model_wikidata.sparql`, `split/model-basics_mardi_*.sparql`, `model-basics_wikidata.sparql` |
| Formula | `split/formulation_mardi_*.sparql`, `formulation_wikidata.sparql`, `split/formulation-basics_mardi_*.sparql`, `formulation-basics_wikidata.sparql` |
| Quantity + Quantity Kind | `split/quantity_mardi_*.sparql`, `quantity_wikidata.sparql` |

**MaRDI Portal queries** (`split/*_mardi_*.sparql`): in each split query, pick
one part other than part 1 with fewer than four `OPTIONAL` blocks (or start a
new part with the next number) and add `?is_dimensional` to its `SELECT` and
`GROUP BY` clauses, then update the table in `split/README.md`.  For model and
formula queries, add a single `OPTIONAL` block with a trailing `BIND`:

```sparql
OPTIONAL {{ ?id wdt:{instance of} wd:{dimensional model}. BIND("True" AS ?is_dimensional_raw) }}
    BIND(COALESCE(?is_dimensional_raw, "False") AS ?is_dimensional)
```

Use `{dimensional formula}` in the formula files.  For the quantity file, both
item types are combined via UNION since only one file covers both:

```sparql
OPTIONAL {{ {{ ?id wdt:{instance of} wd:{dimensional quantity}. }} UNION {{ ?id wdt:{instance of} wd:{dimensional quantity kind}. }} BIND("True" AS ?is_dimensional_raw) }}
    BIND(COALESCE(?is_dimensional_raw, "False") AS ?is_dimensional)
```

**Wikidata queries** (`*_wikidata.sparql`): the items "dimensional model",
"dimensional formula", "dimensional quantity", and "dimensional quantity kind"
do not currently exist in Wikidata, so there is nothing to add to the Wikidata
SPARQL queries.  Should these items be created in Wikidata in the future, the
corresponding blocks can be added at that point using the actual Wikidata QIDs.

---

## Case 2 — Class-Independent: is physical constant

### Step 1a — Add the Option to RDMO

Create a new option with the URI
`https://rdmo.mardi4nfdi.de/terms/options/mathmoddb/is-physical-constant` and
add it to the relevant optionset.  For *is physical constant* the relevant
optionset is:

- `https://rdmo.mardi4nfdi.de/terms/options/quantity-properties`

See [How to Create a New Option](../rdmo/add-option.md)
and [How to Create a New Optionset](../rdmo/add-optionset.md)
for further information.

### Step 1b — Register the Option in `model/data/mapping.json`

```json
{"key": "is_physical_constant", "url": "https://rdmo.mardi4nfdi.de/terms/options/mathmoddb/is-physical-constant", "label": "is physical constant"}
```

### Step 2 — Register MaRDI Portal QIDs

A single item is shared across all entity classes:

**data/items.json:**

```json
"physical constant": "Q6534290"
```

**data/items_staging.json:**

```json
"physical constant": "Q1777"
```

### Step 3 — `model/constants.py`

**3a** — Mutual exclusion pairs (*is physical constant* is mutually exclusive
with both *is mathematical constant* and *is chemical constant*):

```python
data_properties_check = [
    ...
    ('is_mathematical_constant', 'is_physical_constant'),
    ('is_physical_constant',     'is_chemical_constant'),
]
```

**3b** — Entity classes (*is physical constant* applies to quantities and
quantity kinds only):

```python
data_properties_per_class = {
    'quantity': [..., 'is_physical_constant'],
}
```

**3c** — Register as class-independent.  The second element is the full item
name used for all entity classes:

```python
INDEPENDENT_PROPERTIES = [
    ...
    ('is_physical_constant', 'physical constant'),
]
```

### Step 4 — SPARQL Queries

Only the quantity queries need updating: one part of
`split/quantity_mardi_*.sparql` (as in Case 1) and `quantity_wikidata.sparql`.

Add `?is_physical_constant` to `SELECT` and `GROUP BY` of that part and of the
Wikidata query, then add the `OPTIONAL` block in the `WHERE` clause.

**MaRDI Portal:**

```sparql
OPTIONAL {{ ?id wdt:{instance of} wd:{physical constant}. BIND("True" AS ?is_physical_constant_raw) }}
    BIND(COALESCE(?is_physical_constant_raw, "False") AS ?is_physical_constant)
```

**Wikidata:** "physical constant" exists in Wikidata as
[Q173227](https://www.wikidata.org/wiki/Q173227), so the corresponding block
should be added to the Wikidata query:

```sparql
OPTIONAL {{ ?id wdt:P31 wd:Q173227. BIND("True" AS ?is_physical_constant_raw) }}
    BIND(COALESCE(?is_physical_constant_raw, "False") AS ?is_physical_constant)
```
