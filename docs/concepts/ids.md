# Item IDs

Every item in a MaRDMO project has an ID, stored as the `external_id` of its
ID answer:

| ID | Item |
|---|---|
| `mardi:<QID>` | an item of the MaRDI Portal |
| `wikidata:<QID>` | an item of Wikidata |
| `user:<uuid>` | an item of the user's own, not on the portal yet |

The ID dropdown of a page offers **new item** to add an own item (its option
ID is `not found`).  Before the answer is saved, MaRDMO replaces it by a new
`user:` ID (`MaRDMO.ids.assign_id`, called
by the pre-save router), whoever saves it: the interview, a project import or
MaRDMO itself.  The interview shows what the server returns, so the field has
the real ID at once.  An answer that has a `user:` ID already keeps it:
selecting **new item** again does not make a new item.  Name and short
description are typed in their own questions on the page; changing them
renames the item, the ID dropdown only says which item the page is.

This holds for every answer that holds an item: the ID of every page
(`<section>/id`), the items entered on a page without one of their own
(programming languages, CPU models, instruments, methods, and in the workflow
catalog research fields and algorithmic tasks), and relations.

## Relations

A relation holds the ID of the item it refers to; its text is only what the
dropdown showed.

- **An item of the project** is offered with the ID of its page; selecting
  it stores that ID.
- **A new item**: the relation dropdowns offer the typed text as a new item.
  It is the item's label, as typed: "Navier-Stokes (incompressible)" is not
  split into label and description.  Selecting it gives the relation a new
  `user:` ID, and MaRDMO creates the item's page with the same ID and the
  typed name; the short description is entered on the page.  This always
  makes a new page, also when an item of the project has the same label: two
  items may share it.  A page made by mistake is deleted, and the relation
  set to the right item.
- **A new item without a page** stays on the page where it was entered:
  programming languages, CPU models, methods and instruments, and in the
  workflow catalog research fields and algorithmic tasks.  Preview, checks
  and export give it the generic description of its kind
  (`MaRDMO.helpers.describe_items_without_page`; not stored in the project):

    | Item | Description |
    |---|---|
    | programming language | programming language |
    | CPU model | cpu model |
    | method | experimental method |
    | instrument | instrument |
    | research field (workflow catalog) | academic discipline |
    | algorithmic task (workflow catalog) | algorithmic task |

    The same label is the same item: the export creates it once, and finds it
    on the MaRDI Portal if it is there already (the user then selects it).

Preview, checks and export find the page of a relation by its ID and use the
page's name and description (`MaRDMO.helpers.link_to_pages`), so a page
renamed later is shown and exported with its new name.  A relation to an own
item whose page is not there is reported ("Selected … not found in …
Section"), as are two own pages of a section with the same name and
description (the export would make one item of them).

## When the name or description of a page changes

Saving the name or short description of a page in the interview gives every
answer that refers to its item the new text (`MaRDMO.ids.sync_text`):
"Label (Description)", "Label" without description, as the dropdowns
show it.  The source is not part of a text: the dropdowns show it as a grey
tag (**[mardi]**, **[wikidata]**, **[project]**, **[new]**), the preview by
the ID; a text with a tag from an older project is read without it.  The answers are written with `update()`: they keep their
`updated` time, so an interview open on another page can still save them;
it shows the new text when the page is opened again.

Changing the name renames the item everywhere: MaRDMO cannot tell a typo fix
from another item.  To document another item, add a new page (and delete the
old one if it is not needed).

Not synced: the page's own ID answer (for an own item it says "new item"),
a page without name, and saves outside the interview (hydration and imports
bring their texts along).  Preview, checks and export use the page's name
and description anyway.

## When the ID of a page changes

Switching a page to another item changes no other answer: relations stay
with the old item, and the checks report those whose item has no page left.
The user decides once whether an item is on the portal or Wikidata; only the
export changes IDs afterwards (see below).

| Change | Meaning | ID of the page |
|---|---|---|
| `user:` → new item | selected again | keeps its `user:` ID |
| `mardi:` / `wikidata:` → new item | the page is the template of a new item | a new `user:` ID |
| any other change | another item | the selected item's ID |

Publications are no templates: a publication is either on the portal or
Wikidata, or the user's own and entered with its DOI.  Saving the ID of a
publication page clears the data of the previous one.

## Deleting a page

Deleting the tab of an item removes every answer in the project that refers
to it, matched by the exact ID: relations, assumptions, publication
relations, for own and portal items alike (`MaRDMO.ids.remove_references`).
A relation row (relation type, targets and assumptions of one block) whose
last target is removed loses its relation type and assumptions too; a row
with other targets keeps them.

Nothing is removed

- when only the ID of a page is cleared (the tab is still there, another
  item may be selected next);
- when another page still has the item's ID (a copied tab, see below): the
  relations now refer to that page;
- in the usage blocks of a process step (algorithm with software and
  hardware, method with instrument): only the deleted item is removed, the
  checks report the missing one.

The interview shows the removed answers on other pages until they are
opened again.

## Copied tabs

"Copy tab" copies a page with its ID, so the copy is the same item as the
original; MaRDMO does not change it (RDMO writes the copy without signals).
Checks and preview report both pages as one item ("Same Item as Page …"),
since the export would merge them.  Deleting either page leaves the
relations with the other one, which has the item's ID.

A copy of a portal or Wikidata item becomes a new item by choosing "new
item" as its ID (a template, see above).  A copy of an own item stays the
same item; delete one of them.

## In the export

The user's own items with the same name and description are one item: the
same new programming language on two software pages is created once.  The
export item keeps the `user:` IDs it stands for (`user_ids`, not sent to the
portal); afterwards every answer with one of them gets the new `mardi:` ID
and the text "Label (Description)" (`MaRDMO.helpers.replace_ids`).
Answers with the ID of an exported Wikidata item get its new `mardi:` ID too.

## Using a portal item instead

An item the export would create may exist on the MaRDI Portal already (the
same label and description, or for a Wikidata item the same Wikidata QID).
The preview lists these; **Use portal item** (`MaRDMO.duplicates.reuse`) makes
the item the portal item: every answer with one of its IDs (all `user:` IDs
the export would merge, or its `wikidata:` ID) gets `mardi:<QID>` and the
text "Label (Description)" of the portal item, and its page the portal item's
name and description.  Like `replace_ids`, it writes with `update()`, without
MaRDMO's handlers.  Items without a page of their own (e.g. a programming
language) change only in the answers that refer to them.

## Authors and journals of publications

The preview writes the authors and the journal of a publication from its
citation each time again (background answers, no questions).  An author or
journal that is neither on the MaRDI Portal nor on Wikidata gets a `user:`
ID derived from its first identifier (`MaRDMO.ids.part_id`: ORCID iD,
zbMATH author ID, Wikidata QID or name; ISSN, Wikidata QID or title), so it
has the same ID in every preview and in every publication.  The export
knows from where it is (author or journal of a publication) what to create:
a person with ORCID iD / zbMATH author ID (not created without either), or
a journal with its ISSN; afterwards `replace_ids` gives it its `mardi:` ID.
If the MaRDI Portal has it already, the export uses that item instead or
creates it with its identifier in the description (see
[Export Pipeline](export.md#6-payload-construction)); the user never decides
for authors and journals.

## Projects made before MaRDMO 0.8.0

Before 0.8.0, own items had `not found` as their ID, and relations to them
only their text.  Such projects are not supported: the checks report every
page with an answer without a real ID ("Made with MaRDMO before 0.8.0, not
supported"), so the export stops.
