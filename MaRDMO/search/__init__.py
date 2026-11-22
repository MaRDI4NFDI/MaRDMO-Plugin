"""The search catalog: searches the MaRDI Portal for models, algorithms and workflows.

- :mod:`~MaRDMO.search.catalog` — the declaration of the catalog (#198).
- :mod:`~MaRDMO.search.worker` — Background worker that builds and executes
  SPARQL queries for the three search modes (workflow, model, algorithm) and
  returns matching portal items.
- :mod:`~MaRDMO.search.sparql` — Parameterised SPARQL query templates and
  filter fragments for all three search modes, assembled at runtime.

Its dropdowns are MaRDMO's option set provider (:mod:`MaRDMO.providers`).
"""
