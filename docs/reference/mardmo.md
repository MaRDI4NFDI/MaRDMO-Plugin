# Entry Points

Where the export happens, from the answers to the portal:

| Step | Module |
|---|---|
| Read the answers, add pages and IDs | `main`, `project.answers`, `project.pages`, `core.config`, `core.ids` |
| Check and preview | `checks`, `pipeline`, `views` |
| Build the payload | the catalog's `worker` on `export.worker`, `payload` (`bodies`, `claims`, `validation`) |
| Authorize | `oauth2` |
| Post it, report what went wrong | `upload`, `portal_errors` |
| Write the new IDs back | `export.items` (`replace_ids`), `project.writes` |

Every request to an external service goes through `sources/`: `http` (one
session, retries, time limits), `sparql` (the queries and their files), `wikibase` (entities of the MaRDI Portal and
Wikidata), `portal`, `wikidata` and `citations`.  The options of the dropdowns
are `components.dropdowns`.

Shared utilities (values, relations, ordering, properties) are listed under
[Utilities](utilities.md).  The catalogs declare themselves (`catalog.py` of each catalog package, see
[Catalogs](#catalogs-registry) and [How to add a catalog](../how-to/rdmo/add-catalog.md#in-mardmo)).

## Main

::: MaRDMO.main

## Catalogs (registry)

::: MaRDMO.core.catalogs

## OAuth2

::: MaRDMO.oauth2

## Upload

::: MaRDMO.upload

## Export Base

::: MaRDMO.export.worker

## Portal Errors

::: MaRDMO.portal_errors

## Store

::: MaRDMO.store

## Providers

::: MaRDMO.providers

## Option Set Providers (setting)

::: MaRDMO.optionsets

## Option Set Providers (table)

::: MaRDMO.core.searches

## Dropdown Options

::: MaRDMO.components.dropdowns

## Handlers

::: MaRDMO.handlers

## Handler Base

::: MaRDMO.handler_base

## Adders

::: MaRDMO.adders

## Router

::: MaRDMO.router

## Builders

::: MaRDMO.builders

## Validators

::: MaRDMO.validators

## Views

::: MaRDMO.views

## Result Page

::: MaRDMO.success
