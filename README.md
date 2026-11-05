<div align='center' style="margin-top: 50px; font-size: 14px; color: grey;">
  <img src="https://github.com/user-attachments/assets/98c92c58-9d31-41ca-a3ca-189bbfb92101" />
  <p>MaRDMO Logo by <a href="https://www.mardi4nfdi.de/about/mission" target="_blank" style="color: grey;">MaRDI</a>, licensed under <a href="https://creativecommons.org/licenses/by-nc-nd/4.0/" target="_blank" style="color: grey;">CC BY-NC-ND 4.0</a>.</p>
</div>


# MaRDMO Plugin

This repository contains the MaRDMO Plugin for the [Research Datamanagement Organiser](https://rdmorganiser.github.io/) (RDMO) developed within the [Mathematical Research Data Initiative](https://www.mardi4nfdi.de/about/mission) (MaRDI). 

The plugin allows a standardized documentation of:

<ol>
  <li>Algorithms</li>
  <li>Interdisciplinary Workflows</li>
  <li>Mathematical Models</li>
</ol>

Model documentation in MaRDMO follows the [MathModDB ontology](https://portal.mardi4nfdi.de/wiki/MathModDB). Within the plugin, users can record a model, related formulas, computational tasks, quantities or quantity kinds, research problems, academic disciplines, and publications. These inputs are gathered in a guided interview, enabling MaRDMO to produce metadata that is directly compatible with the MaRDI Knowledge Graph. A demo video showing the documentation process for a mathematical model in MaRDMO is available [here](https://www.youtube.com/watch?v=UmbBNUZJ994&list=PLgoPZ7uPWbo-jqDXzx4fSm_4JyAYEMPjn).

Workflow documentation follows a [standardized scheme](https://portal.mardi4nfdi.de/wiki/MD_UseCases) developed in MaRDI. Within the plugin, users can record a workflow, related models, algorithms, methods, software, hardware, experimental equipments, data sets, and publications. These inputs are gathered in a guided interview, enabling MaRDMO to produce metadata that is directly compatible with the MaRDI Knowledge Graph.

Algorithm documentation in MaRDMO follows the [MathAlgoDB ontology](https://portal.mardi4nfdi.de/wiki/Service:6534228). Within the plugin, users can record an algorithm, related algorithmic tasks, implementing software, benchmarks, and publications. These inputs are gathered in a guided interview, enabling MaRDMO to produce metadata that is directly compatible with the MaRDI Knowledge Graph. A demo video showing the documentation process for an algorithm in MaRDMO is available [here](https://www.youtube.com/playlist?list=PLgoPZ7uPWbo-aC9pnVMYRZYM3iygBYWwn).

Completed documentations in MaRDMO can be exported directly from RDMO to the MaRDI Knowledge Graph via the **Export to MaRDI Portal** button. This feature generates a concise summary of the documented model, algorithm, or workflow, and - after user authentication - submits the metadata to the MaRDI Knowledge Graph. This streamlines the publication process and ensures the documentation becomes immediately discoverable within the MaRDI ecosystem. 

In addition to documentation, MaRDMO provides a dedicated interview for searching existing workflows, algorithms, and models. Users can specify individual search parameters related to the underlying ontologies. The **Query MaRDI Portal** button will generate the corresponding SPARQL query based on the user input. The query results are displayed directly in RDMO, enabling researchers to discover and reuse existing knowledge - thus closing the knowledge transfer loop within the MaRDI ecosystem. A demo video showing the search of a model in MaRDMO is available [here](https://www.youtube.com/watch?v=hd3PrlPV3EA).
  
## MaRDMO Plugin Installation

<!-- --8<-- [start:requirements] -->
MaRDMO requires Python 3.10 or later and RDMO 2.5.1 or later. Follow the installation / update instructions of [RDMO](https://rdmo.readthedocs.io/en/latest/installation) if required.
<!-- --8<-- [end:requirements] -->

<!-- --8<-- [start:install] -->
Go to the `rdmo-app` directory of your RDMO installation. In the virtual environment of the RDMO installation install the MaRDMO Plugin:

```bash
pip install MaRDMO
```

To connect the MaRDMO Plugin with the RDMO installation add the following lines to `config/settings/local.py` (if not already present):

```python
from django.utils.translation import gettext_lazy as _ 
``` 

```python
INSTALLED_APPS = ['MaRDMO'] + INSTALLED_APPS

PROJECT_EXPORTS += [
        ('wikibase', _('Export to MaRDI Portal'), 'MaRDMO.main.MaRDMOExportProvider'),
        ('wikibase-search', _('Query MaRDI Portal'), 'MaRDMO.main.MaRDMOQueryProvider'),
        ]

# All option set providers of MaRDMO (the questionnaire's option sets name them by key)
from MaRDMO.optionsets import OPTIONSET_PROVIDERS as MARDMO_OPTIONSET_PROVIDERS
OPTIONSET_PROVIDERS += MARDMO_OPTIONSET_PROVIDERS

```

Up to MaRDMO 0.6 the settings listed the providers one by one (`MaRDMO.model.providers.MathematicalModel` and so on); these classes no longer exist, so replace such a list by the two lines above. Providers of later MaRDMO versions then need no change of the settings.

In addition add the following urlpattern to `config/urls.py`:

```python
path('services/', include("MaRDMO.urls")),
```

Thereby, the MaRDMO Plugin is installed and "Export to MaRDI Portal" and "Query MaRDI Portal" buttons are added in the project view.
<!-- --8<-- [end:install] -->

## MaRDI Portal and Wikidata Connections

<!-- --8<-- [start:connection] -->
Add the following lines to `config/settings/local.py` to connect MaRDMO with the individual databases.

```python
MARDMO_PROVIDER = {
    'mardi': {
        'items': 'data/items.json',
        'properties': 'data/properties.json',
        'api': 'https://portal.mardi4nfdi.de/w/api.php',
        'sparql': 'https://query.portal.mardi4nfdi.de/sparql',
        'uri': 'https://portal.mardi4nfdi.de',
        'entity_uri': 'http://portal.mardi4nfdi.de',
        'oauth2_client_id': '',
        'oauth2_client_secret': '',
    }
}
``` 
Contact the MaRDI consortium for the individual credentials. Wikidata needs no configuration; its endpoints are built into MaRDMO.

Formulas entered in the questionnaires are checked with the TeX checker of the MaRDI Portal before the export, so the RDMO server needs to be able to reach the MaRDI Portal. No credentials are needed for this check.
<!-- --8<-- [end:connection] -->

## MaRDMO-Questionnaire        

<!-- --8<-- [start:questionnaire] -->
The MaRDMO Plugin requires the [MaRDMO-Questionnaire](https://github.com/MaRDI4NFDI/MaRDMO-Questionnaire), download its latest release [![Latest Release](https://img.shields.io/github/v/release/MaRDI4NFDI/MaRDMO-Questionnaire)](https://github.com/MaRDI4NFDI/MaRDMO-Questionnaire/releases/latest).

Integrate the MaRDMO Questionnaire into your RDMO instance through the user interface of your RDMO instance (`Management -> Import -> attributes.xml/optionsets.xml/conditions.xml/catalogs.xml`) or via 

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
<!-- --8<-- [end:questionnaire] -->

## Usage of MaRDMO Plugin

Once the MaRDMO Plugin is set up, the Questionnaires can be used to document and query interdisciplinary workflows, mathematical models, and algorithms. Therefore, select "Create New Project" in RDMO, choose a proper project name (for interdisciplinary workflow the project name will the workflow name), assign one of the MaRDMO Catalogs and select "Create Project". The project is created. Choose "Answer Questions" to start the Interview. Once the Interview is completed, return to the Project Page. On the right hand side in the "Export" section the "Export to MaRDI Portal" and "Query MaRDI Portal" buttons are located to process and subsequently export the completed Questionnaires or query the MaRDI Portal.     

