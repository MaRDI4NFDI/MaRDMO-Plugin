# Export

The way from the answers to the MaRDI Portal (see
[Export Pipeline](../concepts/export.md)):

| Step | Module |
|---|---|
| Read the answers, add pages and IDs | `main`, `project.answers`, `project.pages`, `core.ids` |
| Check and preview | `export.pipeline`, `export.checks` and the catalogs' checks ([Checks](checks.md)), `export.duplicates`, `views` |
| Build the payload | the catalog's `worker` on `export.worker`, `export.payload` ([Payload](payload.md)) |
| Authorize | `export.oauth2` |
| Post it, report what went wrong | `export.upload`, `export.portal_errors` |
| Write the new IDs back | `export.items` (`replace_ids`), `project.writes` |

## Export Base

::: MaRDMO.export.worker

## Items of an Export

::: MaRDMO.export.items

## Duplicates

::: MaRDMO.export.duplicates

## Relations

::: MaRDMO.export.relations

## Ordering

::: MaRDMO.export.ordering

## OAuth2

::: MaRDMO.export.oauth2

## Upload

::: MaRDMO.export.upload

## Portal Errors

::: MaRDMO.export.portal_errors

## Store

::: MaRDMO.export.store

## Result Page

::: MaRDMO.export.success
