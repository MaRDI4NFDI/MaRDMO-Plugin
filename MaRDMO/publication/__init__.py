"""The publications of a documentation: a part every catalog has, not a catalog of its own.

- :mod:`~MaRDMO.publication.models` — Dataclasses for Author, Journal, and
  Publication entities populated from SPARQL results, Crossref, DataCite,
  DOI resolution, zbMath, and ORCID APIs.
- :mod:`~MaRDMO.publication.handlers` — Signal handlers that fetch
  publication metadata and fill the questionnaire when a citation ID is saved.
- :mod:`~MaRDMO.publication.worker` — the citation of a publication, looked up
  by its DOI and written into the questionnaire.
- :mod:`~MaRDMO.publication.utils` — Helper functions for querying external
  citation APIs, resolving ORCiDs, and cleaning bibliographic data.
- :mod:`~MaRDMO.publication.constants` — Field mappings and relation lists used
  when writing publication data to the questionnaire and the MaRDI Portal.

Its export: :class:`MaRDMO.export.worker.CatalogExport`; the relations a
publication can have in each catalog are the catalogs' (``routing``).
"""
