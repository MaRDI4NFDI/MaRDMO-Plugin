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

This holds for every answer that holds an item: the ID of every page
(`<section>/id`), the items entered on a page without one of their own
(programming languages, CPU models, instruments, methods, and in the workflow
catalog research fields and algorithmic tasks), and relations.

## Relations

A relation holds the ID of the item it refers to; its text is only what the
dropdown showed.

- **An item of the project** is offered with the ID of its page; selecting
  it stores that ID.
- **A new item**: the relation dropdowns offer the typed label as a new item
  ("Label", or "Label (Description)").  Selecting it gives the relation a new
  `user:` ID, and MaRDMO creates the item's page with the same ID, with the
  typed name (and description).  This always makes a new page, also when an
  item of the project has the same label: two items may share it.  A page
  made by mistake is deleted, and the relation set to the right item.
- In a catalog without a section for the item (research fields and
  algorithmic tasks in the workflow catalog), the new item stays on the page
  where it was entered.

Preview, checks and export find the page of a relation by its ID and use the
page's name and description (`MaRDMO.helpers.link_to_pages`), so a page
renamed later is shown and exported with its new name.  A relation to an own
item whose page is not there is reported ("Selected … not found in …
Section"), as are two own pages of a section with the same name and
description (the export would make one item of them).

## When the ID of a page changes

Answers that hold the ID of a page follow it only if the page stays the same
item and only its ID becomes known (relations only refer to an item: one
changed to another item moves nothing):

| Change | Meaning | Answers with the old ID |
|---|---|---|
| `user:` → `mardi:` / `wikidata:` | own item found on the portal or Wikidata, or exported | get the new ID |
| `wikidata:` → `mardi:` | Wikidata item on the portal now | get the new ID |
| `mardi:` / `wikidata:` → not found | the page is the template of a new item | stay with the old item |
| `mardi:Q1` → `mardi:Q2` | a correction, or another item | stay with the old item |

The answers are changed with `update()`, so they keep their `updated` time and
an interview open on another page can still save them.  If another page still
has the old ID, they stay with it.

## Copied tabs

"Copy tab" copies a page with its ID, so the copy is the same item as the
original; MaRDMO does not change it (RDMO writes the copy without signals).
Checks and preview report both pages as one item ("Same Item as Page …"),
since the export would merge them.  Deleting either page leaves the
relations with the other one, which has the item's ID.

A copy of a portal or Wikidata item becomes a new item by choosing "not
found" as its ID (a template, see above).

## In the export

The user's own items with the same name and description are one item: the
same new programming language on two software pages is created once.  The
export item keeps the `user:` IDs it stands for (`user_ids`, not sent to the
portal); afterwards every answer with one of them gets the new `mardi:` ID
and the text "Label (Description) [mardi]" (`MaRDMO.helpers.replace_ids`).

## Projects made before MaRDMO 0.8.0

Before 0.8.0, own items had `not found` as their ID, and relations to them
only their text.  Such projects are not supported: the checks report every
page with an answer without a real ID ("Made with MaRDMO before 0.8.0, not
supported"), so the export stops.
