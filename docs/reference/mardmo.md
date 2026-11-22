# Entry Points

Where the export happens, from the answers to the portal:

| Step | Module |
|---|---|
| Read the answers, add pages and IDs | `main`, `project.answers`, `getters`, `pages`, `ids` |
| Check and preview | `checks`, `pipeline`, `views` |
| Build the payload | the catalog's `worker`, `payload` (`bodies`, `claims`, `validation`) |
| Authorize | `oauth2` |
| Post it, report what went wrong | `upload`, `portal_errors` |
| Write the new IDs back | `ids` (`replace_ids`), `writes` |

Every request to an external service (MaRDI Portal, Wikidata, the citation
services) goes through `sources.http`: one session, retries, time limits.

Shared utilities (values, relations, ordering, properties) are listed under
[Utilities](utilities.md).

## Main

::: MaRDMO.main

## Catalogs (table)

::: MaRDMO.catalogs

## OAuth2

::: MaRDMO.oauth2

## Upload

::: MaRDMO.upload

## Portal Errors

::: MaRDMO.portal_errors

## Store

::: MaRDMO.store

## Providers

::: MaRDMO.providers

## Option Set Providers (table)

::: MaRDMO.optionsets

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
