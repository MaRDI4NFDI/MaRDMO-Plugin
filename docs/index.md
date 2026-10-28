# MaRDMO Plugin

<div align="center" style="margin-top: 20px; margin-bottom: 20px;">
  <img src="https://github.com/user-attachments/assets/98c92c58-9d31-41ca-a3ca-189bbfb92101" />
  <p style="font-size: 14px; color: grey;">MaRDMO Logo by <a href="https://www.mardi4nfdi.de/about/mission" target="_blank" style="color: grey;">MaRDI</a>, licensed under <a href="https://creativecommons.org/licenses/by-nc-nd/4.0/" target="_blank" style="color: grey;">CC BY-NC-ND 4.0</a>.</p>
</div>

MaRDMO is a plugin for the [Research Data Management Organiser](https://rdmorganiser.github.io/) (RDMO), developed within the [Mathematical Research Data Initiative](https://www.mardi4nfdi.de/about/mission) (MaRDI). It enables structured documentation and search of mathematical research artifacts through guided questionnaire interviews. Completed documentations can be exported directly to the MaRDI knowledge graph; existing entries can be queried from the MaRDI Portal, MathModDB, or MathAlgoDB and imported back into RDMO.

## Catalogs

MaRDMO provides five catalogs:

| Catalog | Description |
|---------|-------------|
| **Algorithm** | Document algorithms, algorithmic tasks, implementing software, benchmarks, and publications. Based on the [MathAlgoDB ontology](https://portal.mardi4nfdi.de/wiki/Service:6534228). |
| **Interdisciplinary Workflow** | Document workflows, process steps, mathematical models, methods, software, hardware, experimental devices, data sets, and publications. Based on the MaRDI standardised scheme (to some extent on the [Metadata4Engineering (M4E) ontology](https://portal.mardi4nfdi.de/wiki/MD_UseCases)). |
| **Mathematical Model (detailed)** | Document models, mathematical formulations, quantities, quantity kinds, computational tasks, research problems, academic disciplines, and publications. Based on the [MathModDB ontology](https://portal.mardi4nfdi.de/wiki/MathModDB). |
| **Mathematical Model (basic)** | Reduced-scope model documentation using the same MathModDB ontology. |
| **Search** | Query existing entries across the MaRDI Portal, MathModDB, and MathAlgoDB knowledge graphs. Results are displayed directly in RDMO. |

## Prerequisites

- RDMO ≥ 2.5.1 — see the [RDMO installation guide](https://rdmo.readthedocs.io/en/latest/installation) if an update is needed.

## Installation

From the `rdmo-app` directory, install MaRDMO into the RDMO virtual environment:

```bash
pip install MaRDMO
```

Add the following to `config/settings/local.py`:

```python
from django.utils.translation import gettext_lazy as _
```

```python
INSTALLED_APPS = ['MaRDMO'] + INSTALLED_APPS

PROJECT_EXPORTS += [
    ('wikibase',        _('Export to MaRDI Portal'), 'MaRDMO.main.MaRDMOExportProvider'),
    ('wikibase-search', _('Query MaRDI Portal'),     'MaRDMO.main.MaRDMOQueryProvider'),
]
```

The full `OPTIONSET_PROVIDERS` list required for all catalog features is available in the [README](https://github.com/MarcoReidelbach/MaRDMO-Plugin#mardmo-plugin-installation).

Add the following URL pattern to `config/urls.py`:

```python
path('services/', include("MaRDMO.urls")),
```

## Portal Connection

Add the following to `config/settings/local.py` to connect MaRDMO to the MaRDI Portal:

```python
MARDMO_PROVIDER = {
    'mardi': {
        'items':               'data/items.json',
        'properties':          'data/properties.json',
        'api':                 'https://portal.mardi4nfdi.de/w/api.php',
        'sparql':              'https://query.portal.mardi4nfdi.de/sparql',
        'uri':                 'https://portal.mardi4nfdi.de',
        'entity_uri':          'http://portal.mardi4nfdi.de',
        'oauth2_client_id':    '',
        'oauth2_client_secret': '',
    },
}
```

Contact the MaRDI consortium for OAuth2 credentials.  Wikidata needs no
configuration; its endpoints are built into MaRDMO.

Formulas entered in the questionnaires are checked with the TeX checker of the
MaRDI Portal before the export, so the RDMO server needs to be able to reach the
MaRDI Portal.  No credentials are needed for this check.

## Questionnaire Import

MaRDMO requires the [MaRDMO-Questionnaire](https://github.com/MarcoReidelbach/MaRDMO-Questionnaire) — download the [![Latest Release](https://img.shields.io/github/v/release/MarcoReidelbach/MaRDMO-Questionnaire)](https://github.com/MarcoReidelbach/MaRDMO-Questionnaire/releases/latest).

Import via the RDMO management interface (`Management → Import`) or from the command line:

```bash
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/attributes.xml
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/optionsets.xml
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/conditions.xml
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/mardmo-search-catalog.xml
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/mardmo-model-catalog.xml
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/mardmo-model-basics-catalog.xml
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/mardmo-interdisciplinary-workflow-catalog.xml
python manage.py import /path/to/MaRDMO-Questionnaire/catalog/mardmo-algorithm-catalog.xml
```

## Quick Start

1. In RDMO, select **Create New Project**, enter a project name, and assign one of the five MaRDMO catalogs.
2. Select **Answer Questions** to work through the guided interview.
3. Once complete, return to the project page and use the **Export to MaRDI Portal** button (for documentation catalogs) or **Query MaRDI Portal** button (for the search catalog) in the Export section on the right-hand side.

Demo videos are available for [model documentation](https://www.youtube.com/watch?v=UmbBNUZJ994&list=PLgoPZ7uPWbo-jqDXzx4fSm_4JyAYEMPjn) and [algorithm documentation](https://www.youtube.com/playlist?list=PLgoPZ7uPWbo-aC9pnVMYRZYM3iygBYWwn).
