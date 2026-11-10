# Documenting Items

A documentation consists of **items**: models, formulas, quantities, tasks,
algorithms, software, publications, and so on.  Each item has its own tab in
the interview, and the items are linked to each other by **relations**
("the model contains the formula").  This page explains how to add items,
where to change them, and how MaRDMO keeps the links between them.

## Adding an item on its tab

Every tab starts with a question for the item itself.  Type a few characters
to search the MaRDI Portal and Wikidata:

- **The item exists**: select it and **wait** until MaRDMO has filled in what
  the MaRDI Portal knows about it.
- **The item does not exist**: select **new item**.  Then enter its **Name**
  and **Short Description** in the questions below.

## Changing the name or short description

Name and short description are always changed in their own questions on
the item's tab.  A change shows up everywhere the item is used: every
relation to it gets the new name, also on other tabs (open them again to
see it).

Changing the name renames the item; MaRDMO cannot tell a typo fix from a
different item.  **To document another item, add a new tab** instead of
renaming an existing one.

## Linking items

In a relation question ("contains formula", "uses software", ...) type a few
characters and choose from the list.  A grey tag in the open list shows where
each entry comes from:

| Tag | Meaning |
|---|---|
| **[mardi]** | an item of the MaRDI Portal |
| **[wikidata]** | an item of Wikidata |
| **[project]** | an item of this documentation (it has a tab) |
| **[new]** | what you typed: a new item |

Selecting **[new]** creates the item: what you typed is its name, as typed
(it is not split into name and description).  MaRDMO adds a tab for it;
enter its short description there.  Choosing [new] again always creates
another item, also with the same name; to link an item you already added,
choose its [project] entry.

A selected item from the MaRDI Portal or Wikidata gets its own tab too,
filled in by MaRDMO.

### Items without a tab

Some items are entered only where they are used and have no tab of their
own: programming languages, CPU models, methods and instruments, and in the
workflow documentation research fields and algorithmic tasks.  For these,
type the name only; MaRDMO adds a short description of their kind (e.g.
*programming language*).  Use the most specific name (e.g. the model of an
instrument); a generic name such as *microscope* stands for any item of its
kind.  The same name is the same item: if it is on the MaRDI Portal
already, the export asks you to select it.

## Using an item as a template

To start from an existing item of the MaRDI Portal: select it on a new tab,
wait until it is filled in, then select **new item**.  The tab becomes a new
item with the copied content; change its name and short description.
Relations to the original item stay with it.

Publications cannot be used as templates: a publication is either on the
MaRDI Portal or Wikidata, or entered with its DOI.

## Copying and deleting tabs

- **Copy tab** copies the item: both tabs are the same item, and the preview
  and the checks report "Same Item as Page ...".  Delete one of them.
- **Delete tab** removes the item and every relation to it.  A relation
  question that was only filled with this item is emptied.

## Switching an item to another one

Selecting a different item in the first question of a tab does not change
the relations to the old one.  If no tab is left for the old item, the
checks report the relations to it ("Selected ... not found in ...
Section"); link them to the right item again.

## Publications

For a publication of your own, select **new item** and enter its DOI.  The
preview looks up its citation (authors, journal, ...) and shows what the
export creates.  Authors and journals that are not on the MaRDI Portal are
created by the export; an author is created only with an ORCID iD or a
zbMATH author ID.

## After the export

Every new item is created on the MaRDI Portal, and the documentation now
refers to it: its tab and all relations to it show the MaRDI Portal item.

## Documentations made before MaRDMO 0.8.0

MaRDMO 0.8.0 links items by their ID instead of their name.  Documentations
made with earlier versions are not supported: the checks report
"Made with MaRDMO before 0.8.0, not supported (enter it in a new
project)", and the export stops.  Ask the administrators of your RDMO
instance whether they can convert it.
