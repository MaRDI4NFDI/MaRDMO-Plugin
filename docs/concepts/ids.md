# Item IDs

Every item in a MaRDMO project has an ID, stored as the `external_id` of its
ID answer:

| ID | Item |
|---|---|
| `mardi:<QID>` | an item of the MaRDI Portal |
| `wikidata:<QID>` | an item of Wikidata |
| `user:<uuid>` | an item of the user's own, not on the portal yet |

The dropdowns offer **not found** to add an own item.  Before the answer is
saved, MaRDMO replaces it by a new `user:` ID (`MaRDMO.ids.assign_id`, called
by the pre-save router), whoever saves it: the interview, a project import or
MaRDMO itself.  The interview shows what the server returns, so the field has
the real ID at once.  An answer that has a `user:` ID already keeps it:
selecting **not found** again does not make a new item.

This holds for the ID of every page (`<section>/id`) and for the items entered
on a page without one of their own (programming languages, CPU models,
instruments, methods).  These are the questions whose dropdown searches
without the project's answers and offers "not found"; MaRDMO reads them from
the questionnaire (`MaRDMO.ids.id_attributes`).

## When the ID of a page changes

Answers that hold the ID of a page follow it only if the page stays the same
item and only its ID becomes known:

| Change | Meaning | Answers with the old ID |
|---|---|---|
| `user:` → `mardi:` / `wikidata:` | own item found on the portal or Wikidata, or exported | get the new ID |
| `wikidata:` → `mardi:` | Wikidata item on the portal now | get the new ID |
| `mardi:` / `wikidata:` → not found | the page is the template of a new item | stay with the old item |
| `mardi:Q1` → `mardi:Q2` | a correction, or another item | stay with the old item |

The answers are changed with `update()`, so they keep their `updated` time and
an interview open on another page can still save them.  If another page still
has the old ID, they stay with it.

## In the export

The user's own items with the same name and description are one item: the
same new programming language on two software pages is created once.

## Projects made before MaRDMO 0.8.0

Before 0.8.0, own items had `not found` as their ID.  Such projects are not
supported: the checks report every item without a real ID ("Made with MaRDMO
before 0.8.0, not supported"), so the export stops.
