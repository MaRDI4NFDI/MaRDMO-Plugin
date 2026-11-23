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

**File:** `templates/MaRDMO/preview_<catalog>.html` (e.g. `preview_model.html`,
`preview_workflow.html`), with shared blocks in `templates/MaRDMO/partials/`

The answers dict (augmented by pre-processing if applicable) is passed to a Django
template as context.  Add a new section to the relevant template to render the new
entity's fields.  Head each page with `partials/_name.html` (its tab and name); a
relation to a page is resolved by `entity_relations` in pre-processing (an entry
of `preview_relations` in `<submodule>/constants.py`) and is printed as it is:
`{{ relation.relatant }}` renders the link to the page.

!!! note
    The template only shows the answers; it does not decide what is wrong.  The
    checks do (step 3): their problems are attached to the pages, and the template
    shows those of a field with `{% marks values "Field" %}` where it shows the
    field (relation blocks get `field="RelationX"`).  `{% remaining_marks values %}`
    at the end of each page shows the problems no `marks` showed, so a problem is
    never missing from the preview; see [Validation](../../concepts/validation.md).

---

## 3. Validation

**File:** `model/checks.py`, `algorithm/checks.py`, or `workflow/checks.py`

Each catalog has its checks class, a subclass of `ChecksBase`
(`checks/base.py`), which its catalog entry names; its method `run` is the
entry point:

| Method | Catalog scope |
|---|---|
| `ModelChecks.run(project, data, catalog)` | Model catalogs (full and basics) |
| `AlgorithmChecks.run(project, data, catalog)` | Algorithm catalog |
| `WorkflowChecks.run(project, data, catalog)` | Workflow catalog |

These methods validate the collected answers for completeness and consistency and
return a list of `MaRDMO.problems.Problem` (section, page, message, field), made
with `self._error(section, self._page(section_key, index, entry), message,
field='Field')`; the preview lists them under *Before you export* and marks
them on the page where it shows *field*, and the export stops if the list is
not empty.  The message is translated (`_('… {item} …').format(item=…)`), the
section is the English name, marked with `N_('…')` (see
[How to Translate MaRDMO](translate.md)).  Add checks for any
mandatory fields or cross-entity constraints introduced by the new entity.  For
the format of individual values, reuse the shared rules in `components/validators.py` — see
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
type: `"assumes"`.  Forward/backward direction and the role (*object has role*,
e.g. for *contains initial condition*) are read from the mapping data; set
`reverse=True` to override the direction.

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

Qualifiers are either *meaning* or *additive* qualifiers (see
[Qualifier Merge](../../concepts/export.md#qualifier-merge)): a statement that
exists on the MaRDI Portal with the same meaning gets the missing additive
qualifiers instead of being written again.  A new qualifier is additive unless it
is listed in `MEANING_QUALIFIERS` in `payload/claims.py`.  A qualifier that makes a
statement a different one (like a role or a platform) belongs there, and the
property of its statements in `MEANING_PROPERTIES`; the static test
`tests/static/test_meaning_qualifiers.py` checks this for roles and platforms.
