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

To use the MaRDMO Plugin at least `RDMO v2.5.1` is required. Follow the installation / update instructions of [RDMO](https://rdmo.readthedocs.io/en/latest/installation) if required. 

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

OPTIONSET_PROVIDERS = [
    # General
    ('Software', _('Options for Software'), 'MaRDMO.providers.Software'),
    ('RelatedSoftwareWithCreation', _('Options for related Software with Creation'), 'MaRDMO.providers.RelatedSoftwareWithCreation'),
    # Search
    ('ResearchFieldMaRDIOnly', _('Options for Research Fields (MaRDI Only)'), 'MaRDMO.search.providers.ResearchField'),
    ('MathematicalModelMaRDIOnly', _('Options for Mathematical Models (MaRDI Only)'), 'MaRDMO.search.providers.MathematicalModel'),
    ('AlgorithmMaRDIOnly', _('Options for Algorithms (MaRDI Only)'), 'MaRDMO.search.providers.Algorithm'),
    ('SoftwareMaRDIOnly', _('Options for Software (MaRDI Only)'), 'MaRDMO.search.providers.Software'),
    ('HardwareMaRDIOnly', _('Options for Hardware (MaRDI Only)'), 'MaRDMO.search.providers.Hardware'),
    ('MethodMaRDIOnly', _('Options for Methods (MaRDI Only)'), 'MaRDMO.search.providers.Method'),
    ('InstrumentMaRDIOnly', _('Options for Instruments (MaRDI Only)'), 'MaRDMO.search.providers.Instrument'),
    ('DataSetMaRDIOnly', _('Options for Data Sets (MaRDI Only)'), 'MaRDMO.search.providers.DataSet'),
    ('AlgorithmicProblemMaRDIOnly', _('Options for Algorithmic Problems (MaRDI Only)'), 'MaRDMO.search.providers.AlgorithmicProblem'),
    ('ResearchProblemMaRDIOnly', _('Options for Research Problems (MaRDI Only)'), 'MaRDMO.search.providers.ResearchProblem'),
    ('ComputationalTaskMaRDIOnly', _('Options for Computational Tasks (MaRDI Only)'), 'MaRDMO.search.providers.ComputationalTask'),
    ('FormulaMaRDIOnly', _('Options for Formulas (MaRDI Only)'), 'MaRDMO.search.providers.Formula'),
    ('QuantityOrQuantityKindMaRDIOnly', _('Options for Quantities and Quantity Kinds (MaRDI Only)'), 'MaRDMO.search.providers.QuantityOrQuantityKind'),
    # Workflow
    ('MathematicalModelWorkflow', _('Options for Mathematical Model (Workflow)'), 'MaRDMO.workflow.providers.MathematicalModel'),
    ('TaskWorkflow', _('Options for Task (Workflow)'), 'MaRDMO.workflow.providers.Task'),
    ('Hardware', _('Options for Hardware'), 'MaRDMO.workflow.providers.Hardware'),
    ('RelatedHardwareWithCreation', _('Options for related Hardware with Creation'), 'MaRDMO.workflow.providers.RelatedHardwareWithCreation'),
    ('DataSet', _('Options for Data Sets'), 'MaRDMO.workflow.providers.DataSet'),
    ('RelatedDataSetWithCreation', _('Options for related Data Sets with Creation'), 'MaRDMO.workflow.providers.RelatedDataSetWithCreation'),
    ('RelatedInstrumentWithCreation', _('Options for related Instruments with Creation'), 'MaRDMO.workflow.providers.RelatedInstrumentWithCreation'),
    ('RelatedMethodWithCreation', _('Options for related Methods with Creation'), 'MaRDMO.workflow.providers.RelatedMethodWithCreation'),
    ('RelatedAlgorithmWithCreation', _('Options for related Algorithms with Creation'), 'MaRDMO.workflow.providers.RelatedAlgorithmWithCreation'),
    ('ProcessStep', _('Options for Process Step'), 'MaRDMO.workflow.providers.ProcessStep'),
    ('Workflow', _('Options for Workflows'), 'MaRDMO.workflow.providers.Workflow'),
    ('RelatedWorkflowWithoutCreation', _('Options for related Workflows without Creation'), 'MaRDMO.workflow.providers.RelatedWorkflowWithoutCreation'),
    ('RelatedStepWithCreation', _('Options for related Process Steps with Creation'), 'MaRDMO.workflow.providers.RelatedStepWithCreation'),
    ('RelatedProgrammingLanguageWithCreation', _('Options for related Programming Languages with Creation'), 'MaRDMO.workflow.providers.RelatedProgrammingLanguageWithCreation'),
    ('RelatedCPUModelWithCreation', _('Options for related CPU Modelss with Creation'), 'MaRDMO.workflow.providers.RelatedCPUModelWithCreation'),
    ('RelatedHardwareOrSoftwareWithoutCreation', _('Options for related Hardware or Software without Creation'), 'MaRDMO.workflow.providers.RelatedHardwareOrSoftwareWithoutCreation'),
    ('RelatedWorkflowEntityWithoutCreation', _('Options for related Workflow Entities without Creation'), 'MaRDMO.workflow.providers.RelatedWorkflowEntityWithoutCreation'),
    # Model
    ('ResearchField', _('Options for Research Fields'), 'MaRDMO.model.providers.ResearchField'),
    ('RelatedResearchFieldWithCreation', _('Options for related Research Fields with Creation'), 'MaRDMO.model.providers.RelatedResearchFieldWithCreation'),
    ('RelatedResearchFieldWithoutCreation', _('Options for related Research Fields without Creation'), 'MaRDMO.model.providers.RelatedResearchFieldWithoutCreation'),
    ('ResearchProblem', _('Options for Research Problems'), 'MaRDMO.model.providers.ResearchProblem'),
    ('RelatedResearchProblemWithCreation', _('Options for related Research Problems with Creation'), 'MaRDMO.model.providers.RelatedResearchProblemWithCreation'),
    ('RelatedResearchProblemWithoutCreation', _('Options for related Research Problems without Creation'), 'MaRDMO.model.providers.RelatedResearchProblemWithoutCreation'),
    ('MathematicalModel', _('Options for Mathematical Model'), 'MaRDMO.model.providers.MathematicalModel'),
    ('RelatedMathematicalModelWithoutCreation', _('Options for related Mathematical Model without Creation'), 'MaRDMO.model.providers.RelatedMathematicalModelWithoutCreation'),
    ('QuantityOrQuantityKind', _('Options for Quantities and Quantity Kinds'), 'MaRDMO.model.providers.QuantityOrQuantityKind'),
    ('RelatedQuantityWithoutCreation', _('Options for related Quantities without Creation'), 'MaRDMO.model.providers.RelatedQuantityWithoutCreation'),
    ('RelatedQuantityKindWithoutCreation', _('Options for related Quantity Kinds without Creation'), 'MaRDMO.model.providers.RelatedQuantityKindWithoutCreation'),
    ('RelatedQuantityOrQuantityKindWithCreation', _('Options for related Quantites or Quantity Kinds with Creation'), 'MaRDMO.model.providers.RelatedQuantityOrQuantityKindWithCreation'),
    ('MathematicalFormulation', _('Options for Mathematical Formulation'), 'MaRDMO.model.providers.MathematicalFormulation'),
    ('RelatedMathematicalFormulationWithCreation', _('Options for related Mathematical Formulations with Creation'), 'MaRDMO.model.providers.RelatedMathematicalFormulationWithCreation'),
    ('RelatedMathematicalFormulationWithoutCreation', _('Options for related Mathematical Formulations without Creation'), 'MaRDMO.model.providers.RelatedMathematicalFormulationWithoutCreation'),
    ('AllEntities', _('Options for All Entities'), 'MaRDMO.model.providers.AllEntities'),
    ('Task', _('Options for Task'), 'MaRDMO.model.providers.Task'),
    ('RelatedTaskWithCreation', _('Options for related Tasks with Creation'), 'MaRDMO.model.providers.RelatedTaskWithCreation'),
    ('RelatedTaskWithoutCreation', _('Options for related Tasks without Creation'), 'MaRDMO.model.providers.RelatedTaskWithoutCreation'),
    ('RelatedModelEntityWithoutCreation', _('Options for related Model Entities without Creation'), 'MaRDMO.model.providers.RelatedModelEntityWithoutCreation'),
    # Publication
    ('Publication', _('Options for Publication'), 'MaRDMO.publication.providers.Publication'),
    # Algorithm
    ('Algorithm', _('Options for Algorithms'), 'MaRDMO.algorithm.providers.Algorithm'),
    ('RelatedAlgorithmWithoutCreation', _('Options for related Algorithms without Creation'), 'MaRDMO.algorithm.providers.RelatedAlgorithmWithoutCreation'),
    ('AlgorithmicProblem', _('Options for Algorithmic Problems'), 'MaRDMO.algorithm.providers.AlgorithmicProblem'),
    ('RelatedAlgorithmicProblemWithCreation', _('Options for related Algorithmic Problems with Creation'), 'MaRDMO.algorithm.providers.RelatedAlgorithmicProblemWithCreation'),
    ('RelatedAlgorithmicProblemWithoutCreation', _('Options for related Algorithmic Problems without Creation'), 'MaRDMO.algorithm.providers.RelatedAlgorithmicProblemWithoutCreation'),
    ('Benchmark', _('Options for Benchmarks'), 'MaRDMO.algorithm.providers.Benchmark'),
    ('RelatedBenchmarkWithCreation', _('Options for related Benchmarks with Creation'), 'MaRDMO.algorithm.providers.RelatedBenchmarkWithCreation'),
    ('RelatedBenchmarkOrSoftwareWithoutCreation', _('Options for related Benchmarks or Software without Creation'), 'MaRDMO.algorithm.providers.RelatedBenchmarkOrSoftwareWithoutCreation'),
    ]

```

In addition add the following urlpattern to `config/urls.py`:

```python
path('services/', include("MaRDMO.urls")),
```

Thereby, the MaRDMO Plugin is installed and "Export to MaRDI Portal" and "Query MaRDI Portal" buttons are added in the project view.

## MaRDI Portal and Wikidata Connections

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
Contact the MaRDI consortium for the individual credentials.

Formulas entered in the questionnaires are checked with the TeX checker of the MaRDI Portal before the export, so the RDMO server needs to be able to reach the MaRDI Portal. No credentials are needed for this check.

## MaRDMO-Questionnaire        

The MaRDMO Plugin requires the [MaRDMO-Questionnaire](https://github.com/MarcoReidelbach/MaRDMO-Questionnaire), download its latest release [![Latest Release](https://img.shields.io/github/v/release/MarcoReidelbach/MaRDMO-Questionnaire)](https://github.com/MarcoReidelbach/MaRDMO-Questionnaire/releases/latest).

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

## Usage of MaRDMO Plugin

Once the MaRDMO Plugin is set up, the Questionnaires can be used to document and query interdisciplinary workflows, mathematical models, and algorithms. Therefore, select "Create New Project" in RDMO, choose a proper project name (for interdisciplinary workflow the project name will the workflow name), assign one of the MaRDMO Catalogs and select "Create Project". The project is created. Choose "Answer Questions" to start the Interview. Once the Interview is completed, return to the Project Page. On the right hand side in the "Export" section the "Export to MaRDI Portal" and "Query MaRDI Portal" buttons are located to process and subsequently export the completed Questionnaires or query the MaRDI Portal.     

