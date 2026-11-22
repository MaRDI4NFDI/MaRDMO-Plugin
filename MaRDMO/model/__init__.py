"""The model catalogs (full and basics): mathematical models, with MathModDB.

- :mod:`~MaRDMO.model.catalog` — the declaration of the catalogs (#198).
- :mod:`~MaRDMO.model.models` — Dataclasses for MathematicalModel, Task,
  MathematicalFormulation, QuantityOrQuantityKind, ResearchField, and
  ResearchProblem entities from MaRDI Portal or Wikidata.
- :mod:`~MaRDMO.model.handlers` — Signal handlers that populate the
  questionnaire when an external ID is saved.
- :mod:`~MaRDMO.model.checks` — the checks of the catalogs.
- :mod:`~MaRDMO.model.validators` — the catalogs' own pre-save validators.
- :mod:`~MaRDMO.model.worker` — Background worker for generating model previews
  and exporting model entries to the MaRDI Portal.
- :mod:`~MaRDMO.model.utils` — Utility functions for building quantity info and
  mapping entity-quantity relationships.
- :mod:`~MaRDMO.model.constants` — Relation mappings, data-property checks,
  and URI-prefix configurations specific to the model catalogs.
"""
