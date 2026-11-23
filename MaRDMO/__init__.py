"""MaRDMO — Mathematical Research Data Management Organiser plugin for RDMO.

MaRDMO extends the Research Data Management Organiser (RDMO) with questionnaire
catalogs for mathematical research, filled in from the MaRDI Portal and
Wikidata, and exports their documentation to the MaRDI Portal:

- **Mathematical models** (:mod:`MaRDMO.model`) — models, formulations, tasks
  and quantities.
- **Algorithms** (:mod:`MaRDMO.algorithm`) — algorithms, problems, software
  and benchmarks.
- **Interdisciplinary workflows** (:mod:`MaRDMO.workflow`) — process steps,
  methods, software, hardware, instruments and data sets.
- **Portal search** (:mod:`MaRDMO.search`) — SPARQL search across the models,
  algorithms and workflows of the MaRDI Portal.

Below the catalogs are the export (:mod:`MaRDMO.export`), the parts of the
interview (:mod:`MaRDMO.components`, publications by DOI among them), the
project's answers (:mod:`MaRDMO.project`), the external services
(:mod:`MaRDMO.sources`) and what all of them need (:mod:`MaRDMO.core`); each
layer uses only the layers below it (docs: Concepts, Architecture).
"""

__title__ = 'MaRDMO'
__version__ = '0.7.0'
__author__ = 'Marco Reidelbach'
__email__ = 'reidelbach@zib.de'
__license__ = 'Apache-2.0'

VERSION = __version__
