# Handlers

When a user selects an existing item from the MaRDI Portal or Wikidata in a questionnaire field, MaRDMO automatically retrieves and fills in all associated metadata — labels, descriptions, relations, and linked sub-entities — without any manual copying.  This is the job of the *handlers*.

## Signal Wiring

RDMO emits a `value_created` or `value_updated` signal every time a questionnaire answer is saved by the user.  MaRDMO registers signal receivers in `router.py`.

At startup, `build_handler_map()` constructs a nested lookup table:

```
{ catalog_uri: { attribute_uri: handler_method } }
```

On each incoming signal the router checks the active catalog and the URI of the saved attribute, and dispatches to the matching handler method.  A separate `DELETE_HANDLER_MAP` handles cleanup when a value is removed: it deletes all dependent answers that were previously filled in for that entity.

## Why Not Django Signals for the Cascade?

`value_editor()` — the helper that writes answers back into the project — saves values directly to the database.  If these writes triggered Django signals, every programmatic fill would re-activate handlers, creating runaway cascades.

More critically, during an RDMO project import all values are written to the database in bulk while Django signals are already active.  Using signals for the fill cascade would cause handlers to fire out of order against a partially-loaded project, producing incomplete or corrupt results.  MaRDMO therefore uses **direct function calls** for all handler-to-handler cascading, ensuring that fills only happen in response to genuine user interactions.

## Handler Flow

The sequence when a user picks a *Mathematical Model* from the portal:

1. RDMO emits `value_created` / `value_updated` for the model ID field.
2. The router dispatches to `Information.model(instance)`.
3. `model()` calls `_entry()`, which collects the selected QID and calls `_fill_model_batch()`.
4. `_fetch_by_source()` fires a **single SPARQL query** (against MaRDI Portal, and optionally Wikidata) to retrieve the model's metadata.
5. `_fill_model_batch()` writes labels, descriptions, aliases, properties, and relations into the appropriate questionnaire pages via `value_editor()`.
6. For each related sub-entity type (Research Problems, Mathematical Formulations, Computational Tasks, …), `_fill_model_batch()` calls `_hydrate_relatants()`, which in turn calls the corresponding `_fill_*_batch()` method **directly** — no signal is emitted.
7. Each `_fill_*_batch()` call batches its SPARQL query across **all** entities of that type at once.  For example, if the selected model contains ten Mathematical Formulations, all ten are fetched in a single query and then distributed across the ten questionnaire pages.  The same applies to linked Research Problems, Computational Tasks, and so on.
8. A `visited` set is passed through the entire call tree to prevent infinite loops when entities reference each other cyclically.

The batching principle ensures that the number of SPARQL queries scales with the number of distinct *entity types* in the cascade, not with the number of individual entities.

## Database Writes and Network Requests

Selecting a large item writes hundreds of values.  The router therefore runs every
handler inside `helpers.batched_writes()`:

- On PostgreSQL and MySQL, the writes of `value_editor()` are collected in one
  transaction, which is committed before every request to an external service and
  at the end.  The database is never locked while MaRDMO waits for the network.
  If a handler fails, only the writes since the last commit are rolled back.
- On SQLite, every value is still committed on its own.  SQLite locks the whole
  database, and a longer transaction that reads before it writes fails with
  *database is locked* when another user saves at the same time.
- Attributes looked up by URI are remembered until the handler finishes.

All requests to external services go through `queries.http_session()`, which
commits the pending writes and reuses one HTTP session per thread, so repeated
requests to the same service keep their connection open.

## Pre-Save Validation

In addition to the post-save handler dispatch, MaRDMO registers a `pre_save`
receiver on the RDMO `Value` model.  Before an answer is written to the
database, the router looks up the attribute URI in `PRESAVE_VALIDATOR_MAP`
(assembled by `build_presave_validator_map()` in `builders.py`) and calls the
matching validator.  A validator raises `rest_framework.exceptions.ValidationError`
to reject the value; RDMO then shows the message below the question in the
interview.

Only answers saved through the interview are validated.  Writes made by the
handlers themselves run inside `helpers.internal_write()` and skip these
validators, so importing an item never fails because of a pre-save rule;
imported data is checked before the export instead.  The rules, the
places where they are applied, and the exceptions are described in
[Validation](validation.md).
