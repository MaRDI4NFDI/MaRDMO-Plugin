"""The interdisciplinary workflow catalog: research workflows.

- :mod:`~MaRDMO.workflow.catalog` — the declaration of the catalog (#198).
- :mod:`~MaRDMO.workflow.models` — Dataclasses for ProcessStep, Method,
  Software, Hardware, and DataSet entities from MaRDI Portal / Wikidata,
  as well as Variables and Parameters.
- :mod:`~MaRDMO.workflow.handlers` — Signal handlers that populate the
  questionnaire when a software, hardware, instrument, data set, method, or
  process-step ID is saved.
- :mod:`~MaRDMO.workflow.checks` — the checks of the catalog.
- :mod:`~MaRDMO.workflow.worker` — Background worker for generating workflow
  previews and exporting workflow entries to the MaRDI Portal.
- :mod:`~MaRDMO.workflow.utils` — Helpers for partitioning disciplines,
  extracting data-set size, reference, and archive metadata.
- :mod:`~MaRDMO.workflow.constants` — URI-prefix maps and property lists for
  the workflow catalog.
"""
