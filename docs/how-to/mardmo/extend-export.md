# Adding Export Support for a New Entity

When a new entity type is added to a MaRDMO submodule, four stages of the pipeline
need to be extended: pre-processing, HTML preview, validation, and portal export.
This page describes each stage and the helpers available for implementing it.

For the full end-to-end export flow from the user's perspective, see
[Export Pipeline](../../concepts/export.md).

---

## 1. Pre-processing (optional)

**File:** `<submodule>/worker.py` — class `Prepare*`, method `preview`

Before the answers dict is passed to the template, an optional pre-processing step
can augment it with display-ready structures.  This is only needed when nested or
paired data must be flattened or grouped for the template to iterate over directly,
for example:

```python
wf_data['model_task_pairs'] = [...]         # Workflow: models + their tasks
ps_data['algorithm_software_pairs'] = [...]  # Process step: algorithms + software/hardware/docs
ps_data['method_instrument_pairs']  = [...]  # Process step: methods + instruments/docs
hw_data['cpu_entries']              = [...]  # Hardware: CPUs with counts and cores
```

If the new entity's data can be rendered directly from the answers dict without
restructuring, this step can be skipped.

---

## 2. HTML Preview

**File:** `templates/MaRDMO/<catalog>Template.html` (e.g. `modelTemplate.html`,
`workflowTemplate.html`), with shared blocks in `templates/MaRDMO/partials/`

The answers dict (augmented by pre-processing if applicable) is passed to a Django
template as context.  Add a new section to the relevant template to render the new
entity's fields.

!!! note
    Errors (missing required fields, invalid values) are flagged with red text at
    this stage so the user can correct them before committing to the export.
    Value formats are checked with the template filters in
    `templatetags/mardmo_tags.py` (e.g. `url_problem`, `doi_problem`,
    `count_problem`), which use the same rules as the checks and the export;
    see [Validation](../../concepts/validation.md).

---

## 3. Validation

**File:** `checks/model.py`, `checks/algorithm.py`, or `checks/workflow.py`

The `Checks` class (`checks/__init__.py`) composes three mixins, each exposing one
entry-point method:

| Method | Catalog scope |
|---|---|
| `Checks.run_model(project, data, catalog)` | Model catalog |
| `Checks.run_algorithm(project, data, catalog)` | Algorithm catalog |
| `Checks.run_workflow(project, data, catalog)` | Workflow catalog |

These methods validate the collected answers for completeness and consistency and
return an error list that aborts the export if non-empty.  Add checks for any
mandatory fields or cross-entity constraints introduced by the new entity.  For
the format of individual values, reuse the shared rules in `validators.py` — see
[How to Validate a New Field](validate-field.md).

---

## 4. Portal Export

**File:** `<submodule>/worker.py` — class `Prepare*`, method `export`

The `export` method translates the answers dict into Wikibase statements.  The
following helpers are available on the payload object:

### Statement helpers

**`add_answer(verb, object_and_type, qualifier=None, subject=None)`**  
Add a single statement.  Automatically routes to a batch statement (new item) or
a `RELATION` entry (existing item).

```python
payload.add_answer(
    verb            = self.properties["instance of"],
    object_and_type = [item_key, "wikibase-item"],
    qualifier       = qualifiers,
)
```

**`add_answers(mardmo_property, wikibase_property, datatype="string")`**  
Iterate over all values stored under `mardmo_property` in the current subject and
call `add_answer` for each.

```python
payload.add_answers("descriptionLong", "description", datatype="string")
```

### Relation helpers

**`add_single_relation(statement, alt_statement=None, qualifier=None, reverse=False)`**  
Add one statement per entry in `subject[statement["relatant"]]`.  Uses the portal
item key when the relatant is in the payload dictionary; falls back to
`alt_statement` (string value) otherwise.  Set `reverse=True` to swap subject and
object.

**`add_multiple_relation(statement, optional_qualifier=None, reverse=False)`**  
Add one statement per `(relation, relatant)` pair.  Supported optional qualifier
type: `"assumes"`.  Forward/backward direction is read from the mapping data; set
`reverse=True` to override.

### Specialised helpers

**`add_data_properties(item_class)`**  
Add `instance of` statements for each data property checkbox selected on the
current subject (e.g. dimensional, deterministic).

**`add_in_defining_formula()`**  
Add `in defining formula` statements with `symbol represents` qualifiers, used for
mathematical formulations and quantities.

**`add_aliases(aliases_dict)`**  
Add alias statements for the current subject item.

### Qualifier helper

**`add_qualifier(identifier, data_type, content)`**  
Build a qualifier dict to pass to any of the statement helpers above.

```python
qualifiers = payload.add_qualifier(
    self.properties["comment"], "string", comment_text
)
```
