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

<!-- The sections below come from the README (pymdownx.snippets, see mkdocs.yml): edit them there. -->

## Prerequisites

--8<-- "README.md:requirements"

## Installation

--8<-- "README.md:install"

## Portal Connection

--8<-- "README.md:connection"

## Questionnaire Import

--8<-- "README.md:questionnaire"

## Quick Start

1. In RDMO, select **Create New Project**, enter a project name, and assign one of the five MaRDMO catalogs.
2. Select **Answer Questions** to work through the guided interview.
3. Once complete, return to the project page and use the **Export to MaRDI Portal** button (for documentation catalogs) or **Query MaRDI Portal** button (for the search catalog) in the Export section on the right-hand side.

Demo videos are available for [model documentation](https://www.youtube.com/watch?v=UmbBNUZJ994&list=PLgoPZ7uPWbo-jqDXzx4fSm_4JyAYEMPjn) and [algorithm documentation](https://www.youtube.com/playlist?list=PLgoPZ7uPWbo-aC9pnVMYRZYM3iygBYWwn).
