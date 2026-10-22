"""MaRDMO — Mathematical Research Data Management Organiser plugin for RDMO.

MaRDMO extends the Research Data Management Organiser (RDMO) with questionnaire
catalogs and automated metadata retrieval for three research-artifact types:

- **Mathematical models** (:mod:`MaRDMO.model`) — structured documentation of
  models, formulations, tasks, and quantities linked to the MaRDI Portal.
- **Algorithms** (:mod:`MaRDMO.algorithm`) — structured documentation of
  algorithms, problems, software, and benchmarks linked to the MaRDI Portal.
- **Interdisciplinary workflows** (:mod:`MaRDMO.workflow`) — documentation of
  computational workflows including process steps, methods, software, hardware,
  instruments, and data sets.
- **Publications** (:mod:`MaRDMO.publication`) — automated retrieval of
  bibliographic metadata from Crossref, DataCite, DOI, zbMath, and ORCID.
- **Portal search** (:mod:`MaRDMO.search`) — SPARQL-based search across models,
  algorithms, and workflows stored in the MaRDI Portal.

The plugin uses Signal handlers (:mod:`MaRDMO.router`) to react to
questionnaire saves and fills related fields automatically.  Export to the
MaRDI Portal is handled via OAuth2 (:mod:`MaRDMO.oauth2`) with live progress
tracking (:mod:`MaRDMO.store`, :mod:`MaRDMO.views`).
"""

__title__ = 'MaRDMO'
__version__ = '0.6.2'
__author__ = 'Marco Reidelbach'
__email__ = 'reidelbach@zib.de'
__license__ = 'Apache-2.0'

VERSION = __version__
