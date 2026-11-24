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

The list offers only items of the kind the question asks for: software in
a software question, formulas in a formula question, and so on, from the
MaRDI Portal and from Wikidata.  Research problems are an exception: no
Wikidata class fits them, so the list offers everything from Wikidata that
is not plainly something else (a person, a publication, a film, a place,
...).  Process steps are searched on the MaRDI Portal only.

### If the item is not in the list

Type its ID with the prefix of its source: `mardi:Q123` for an item of the
MaRDI Portal, `wikidata:Q42` for one of Wikidata.  The list then offers that
item only, if it is of the kind the question asks for; otherwise it offers
nothing.  An item that was merged into another one is offered as that item.

## Formulas and symbols

Formulas and symbols are entered in LaTeX, without `$...$` or `\(...\)`.
What you type is shown rendered below the field, so you can see whether it
reads as intended.  When you stop typing, MaRDMO asks the MaRDI Portal
whether it accepts the formula; a note below the field means it does not
(it accepts less than LaTeX, e.g. not `gather` or `align*`), or that the
formula cannot be shown at all.  What you typed is never changed.

A formula or quantity has **one** defining formula; a system of equations
is one formula (e.g. in an `align` environment).

Below the formula, its symbols and the quantities they stand for.  A symbol
that stands for the **same quantity in all formulas** of the documentation
is entered **once**, in any formula or quantity definition: every other
formula that uses it gets it from there, and the preview shows such a row
with *cf. page …*, the page it comes from.  A symbol that stands for
**different quantities** (`h` the hormone level in one model, the insulin
level in another) is entered in **every** formula that uses it; a formula
that uses it without its own row cannot be exported until it has one.  The
preview also names letters of a formula that no symbol table defines, in
case they stand for quantities.

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
characters and choose from the list, or type an item's ID as above.  A
coloured tag in the open list shows where each entry comes from:

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

### Items from Wikidata

An item you select from Wikidata is filled completely, and it brings the
items it relates to: the quantities of its defining formula, the
dependencies and programming languages of a software, the research problem
and tasks of a model, the algorithms and software of a process step, ...
For each of these:

- **The MaRDI Portal has the item already** (as the same Wikidata item, and
  of the kind the relation asks for, e.g. software for a dependency): MaRDMO
  uses the portal's item, with its name and description.  An item with a tab
  is filled from the MaRDI Portal.
- **Otherwise** the item stays a Wikidata item.  If it has a tab, the tab
  gets its name and short description only: MaRDMO does not follow its
  relations on Wikidata, which often form long chains (Ohm's law alone would
  bring almost 70 quantities, a software its whole dependency tree).
  Complete such an item yourself if you need more of it, e.g. the class and
  definition of a quantity (written with `\equiv`).

An item that has a tab in your documentation already keeps it, also when it
is from Wikidata.  A Wikidata publication also becomes the MaRDI Portal's if
the portal has it by its DOI; one without DOI stays a Wikidata publication.

### Items without a tab

Some items are entered only where they are used and have no tab of their
own: programming languages, CPU models, methods and instruments, and in the
workflow documentation research fields and algorithmic tasks.  For these,
type the name only; MaRDMO adds a short description of their kind (e.g.
*programming language*).  Use the most specific name (e.g. the model of an
instrument); a generic name such as *microscope* stands for any item of its
kind.  The same name is the same item: if it is on the MaRDI Portal
already, the export asks you to select it.

## A tab is the item

Every relation you make links to a tab, and it stays with that tab whatever
you later choose as its item: a new item, a MaRDI Portal item or a Wikidata
item.

## Using an item as a template

To start from an existing item of the MaRDI Portal: select it on a new tab,
wait until it is filled in, then select **new item**.  The tab becomes a new
item with the copied content; change its name and short description.  The
relations to the tab stay with it, now with the new item.  To keep the
portal item as it is and make a new one from it, copy its tab first and
change the copy (see below).

Publications cannot be used as templates: a publication is selected by its
identifier.

## Copying and deleting tabs

- **Copy tab** makes a new item from the tab: change the copy's name and
  short description (the preview and the checks report a copy whose name
  and short description are still the original's).  The relations stay
  with the original.  A copy of a MaRDI Portal or Wikidata item is still
  that item ("Same Item as Page ..."): make the copy a new item, or choose
  another item for it.  Until you open the copy's page again, its first
  question still shows the original's ID; that changes nothing.
- **Delete tab** removes the item and every relation to it.  A relation
  question that was only filled with this item is emptied.  Delete the copy,
  not the original, if you want to keep the relations; the copy is the tab
  added last.  A copy of a portal item that is left after deleting its
  original takes the relations over.

## Switching an item to another one

Selecting a different item in the first question of a tab takes the
relations to the tab along: they now refer to the new item.  This also holds
for relations on tabs of MaRDI Portal items: the export adds them to those
portal items.  If two tabs have the same item, the relations belong to the
first of them.  While the first question of a tab is empty, its relations
wait for the next item chosen there; the checks report the tab without ID
meanwhile.

The content of the tab stays, and what the newly chosen item brings is
added.  If you picked the wrong item, delete the tab and add a new one
rather than choosing another item on it: the wrong item's content and the
tabs MaRDMO added for it would stay.

## Publications

A publication is selected by its identifier, not by its title: type it with
its prefix, for now `doi:` and the DOI (`doi:10.1007/BF01386390`; a pasted
`https://doi.org/…` link after `doi:` works too).  The dropdown offers

- the publication of the MaRDI Portal, if the portal has the DOI;
- otherwise the publication of Wikidata, if Wikidata has it;
- otherwise the DOI itself, marked **new**: a publication the export creates.

An invalid DOI is offered as well, so that saving it says what is wrong with
it; it is not saved.  For a new publication the field keeps `doi:…`, and
MaRDMO looks up its citation (title, authors, journal, …) in the background
from the MaRDI Portal, Wikidata, Crossref, DataCite, zbMATH and doi.org; you
can go on with the interview meanwhile.  If none of them knows the DOI, the
preview says so: check the DOI, or open the preview again later.  The
preview shows what the export creates.  Authors and journals that are not
on the MaRDI Portal are created by the export; an author is created only
with an ORCID iD or a zbMATH author ID.

The name and short description of a publication are those of its citation;
you cannot change them.

## Items that are already on the MaRDI Portal

The dropdowns offer only MaRDI Portal items of the kind a question asks for.
An item may exist on the portal anyway: with another class and profile or
none (e.g. imported from Wikidata), or not among the results.  The export would create
it a second time, so the preview lists such items at the top, in the box
**Before you export** under **Items already on the MaRDI Portal**, and
the export button stays disabled until none is left.  Each item shows its
source (*new* or *Wikidata*), name and short description; below it where you
entered it (page and tab, linked to the interview), the portal item to check
(linked to the MaRDI Portal), and your decision.  Nothing is chosen at first;
a choice shows its button next to it (hover over a choice to read what it
does):

- **Use this item**, then **Apply**: your item becomes the portal item, and
  the preview opens again without it.  Every answer that
  refers to it then refers to the portal item, and its tab gets the portal
  item's name and short description.  The export adds what you documented to
  the portal item.  This can be chosen if the portal item is not another kind
  of item (another class, community or profile type than MaRDMO would give
  it); otherwise it is greyed out, and hovering over it or the small **i**
  next to it says why.
- **Redefine**, then **To interview** (opens in a new window): give
  your item another name or short description on its tab.  For an item you
  selected from Wikidata, choose another item or make it a new item there: a
  new name would not change the Wikidata item.  An item of your own with the
  name and short description of a Wikidata item you selected elsewhere (the
  MaRDI Portal takes only one): rename yours, or select the Wikidata item.
  Then open the preview again.

A publication with the DOI of a portal publication is that publication: it
can only become the portal item (**Use this item**; its tab then shows the
portal item, without the citation looked up before).  If its DOI is wrong,
correct it on its tab.  A publication with the name and short description of
a portal publication with another DOI is another publication: the portal
takes only one item per name and description, so the export creates it with
its DOI in the short description ("… (DOI 10.…)"), and the preview says so
at the publication.  The same holds for two publications of your
documentation with the same name and short description: every one but the
first gets its DOI in it (a Wikidata publication without DOI its Wikidata
QID).  Two tabs with the same DOI are one publication: delete one of them.

Authors and journals of publications are not listed: MaRDMO takes them from
the citation and decides for them itself.

If the MaRDI Portal gets such an item between the preview and the export,
the export stops at it and says what to do: open the preview again, decide,
and export again.  What was created until then stays on the MaRDI Portal and
in your documentation.

## After the export

Every new item is created on the MaRDI Portal, and the documentation now
refers to it: its tab and all relations to it show the MaRDI Portal item.

## Documentations made before MaRDMO 0.8.0

MaRDMO 0.8.0 links items by their ID instead of their name.  Documentations
made with earlier versions are not supported: the checks report
"Made with MaRDMO before 0.8.0, not supported (enter it in a new
project)", and the export stops.  Ask the administrators of your RDMO
instance whether they can convert it.

## Before you export

The preview checks everything the export checks, also against the MaRDI
Portal (for example a symbol that stands for another quantity there).  What
it finds is listed at the top, in the box **Before you export** under
**Errors, inconsistencies and incomplete documentation**, by tab, each linked
to the tab's place in the preview and to its page in the interview.  In the
preview itself a missing answer is marked in red where it belongs (instead
of *NOT DOCUMENTED*, which marks only what may be left out).  The export button is disabled
(hover over it to read why; **To the top** next to it leads back to the box)
until the list is empty: fix the points in the interview and open the
preview again.  If the MaRDI Portal does not answer, the preview says so;
try again shortly with **Check again**.

Items of the MaRDI Portal are not created by the export, so what they lack
does not stop it: a reference of a portal software, the size of a portal
data set, or an invalid value the portal item has already.  The box lists
these under **Portal items you could complete (optional)**, marked in blue,
and the export button stays enabled.  If you complete them in the interview,
the export adds what you entered to the portal item.  A value you add to a
portal item must be valid, as everything MaRDMO writes: an invalid one is
red and stops the export.

The export checks once more.  If something changed since the preview (in
your documentation, or on the MaRDI Portal), it stops before anything is
exported and lists what changed.
