# Export Pipeline

Clicking "Export to MaRDI Portal" on an RDMO project page triggers a two-phase
pipeline.  The **first click** renders a documentation preview; the **second click**
(on the button at the bottom of the preview) performs the authenticated upload.
This page walks through every step in order.

---

## Phase 1 — Preview (first click)

### 1. Catalog Check

`render()` looks up the active project catalog in the template map.  If the catalog
is not one of the supported MaRDMO catalogs, an error page is returned immediately.

### 2. Collecting Answers

`get_post_data('preview')` reads all RDMO project values and assembles them into a
nested answers dict via `process_question_dict()`, organised by entity type (e.g.
`{"model": {...}, "formulation": {...}, "publication": {...}}`).

In preview mode, publication metadata is additionally fetched and merged into the
answers dict, and `prepare.preview()` pre-processes the data into display-ready
structures for the template (e.g. paired algorithm–software entries, model–task
pairs).

Publications taken from Wikidata or entered by the user are looked up by their DOI
(MaRDI Portal, Wikidata, Crossref, DataCite, zbMATH, doi.org, ORCID).  Up to three
publications are looked up at the same time, and the result for a DOI is kept in
Django's cache for an hour, so clicking the preview again does not repeat the
lookups.  A result is only kept if the MaRDI Portal and Wikidata answered and some
source knows the publication; otherwise the next preview looks it up again.

### 3. Preview

The answers dict is passed to the catalog-appropriate Django template, which renders
an **HTML documentation preview** — a human-readable rendering of everything the
user has entered in the questionnaire.  Missing fields and invalid values (URLs,
DOIs, swMATH IDs, numbers, …) are already flagged with red text at this stage,
using the same rules as the checks and the export (see
[Validation](validation.md)), giving the user a chance to review and correct the
documentation before committing to the export.  For model catalogs, every formula
is checked with the MaRDI Portal's TeX checker; rejected formulas are shown as raw
TeX with an explanation.  A second "Export to MaRDI Portal" button at the bottom
of the preview page triggers the actual export.

Publications are shown as the export writes them: a citation line built from the
parts that are known (authors, year, title, journal, volume, issue, pages), what
the export creates on the MaRDI Portal (the publication, its journal, new
authors), and, in a collapsible *Authors and journal* section, every author and
the journal with its status (on the MaRDI Portal, new, or name only) and its
identifiers (ORCiD, zbMath, Wikidata, ISSN).

---

## Phase 2 — Export (second click)

### 4. Credential Check

`submit()` checks that `oauth2_client_id` and `oauth2_client_secret` are present in
the Django settings.  If either is missing, an error page is returned before any
data processing happens.

### 5. Validation Checks

`get_post_data()` re-collects the answers dict (submit mode — without publication
retrieval).  `Checks.run_X()` then validates the collected answers for completeness
and consistency, including the value formats described in
[Validation](validation.md) and, for the detailed model catalog, the formula check
against the MaRDI Portal's TeX checker.  In addition, for every entity that would
be newly created on the MaRDI Portal, a request is sent to check whether an item
with the same label and description combination already exists.  If any check
fails, a readable error list is returned and the export is aborted.

### 6. Payload Construction

`PrepareX().export()` translates the answers dict into a Wikibase-ready payload dict
and a dependency graph:

- **`unique_items()`** deduplicates all entities referenced across the questionnaire.
- **`process_items()`** assigns each unique item to one of two tracks:
    - Items already on the MaRDI Portal (`mardi:` prefix) are registered with their
      real QID.
    - All other items (from Wikidata, or newly defined) are again checked against the
      MaRDI Portal for duplicates (`_check_mardi_and_raise`), then registered as new
      with an empty QID and a seed list of statements (Wikidata QID, ORCiD, zbMath
      code, or ISSN as appropriate).  The searches for all new items run first,
      four at a time; a search that still fails after its retries finds nothing,
      and the MaRDI Portal itself rejects an item whose label and description
      exist already (see below).
- **`add_answer()` calls** accumulate statements:
    - For **new items**: statements are appended to the item's payload and will be
      created together with the item in a single API call.
    - For **existing items**: each statement becomes a separate `RELATION<n>` entry
      that will be posted individually.

    Values are normalised on the way: tabs and outer whitespace are removed from
    text, formulas are put on one line, and quantity amounts lose leading zeros
    (see [Validation](validation.md#normalisation-on-export)).
- **Final check**: `validate_identifiers()` checks every URL, DOI, swMATH ID, date
  and quantity amount in the payload.  If any of them would be rejected by the
  MaRDI Portal, the export is aborted with a list of the affected values before
  anything is posted.
- **Relation existence check**: `build_relation_check_queries()` generates SPARQL
  queries (in chunks of 50 relations) that check, for every `RELATION` entry
  targeting an existing item, whether the statement with its qualifiers already
  exists on the MaRDI Portal.  For `math`-datatype statements a separate
  API-based check is used, because SPARQL returns MathML while the MaRDI Portal
  stores LaTeX.  If a check cannot be completed, the export is aborted, since
  posting without it could create duplicate statements.
- **Qualifier merge**: `merge_qualifiers()` then decides, with the statements
  of the existing items (fetched via `wbgetentities`, 50 items per request,
  shared with the math check), what happens with each `RELATION` entry (see
  [below](#qualifier-merge)): it exists already and is skipped, it is a new
  statement, or it exists and only gets the qualifiers it lacks.

All requests of these checks (duplicate search, relation and math check,
statements for the qualifier merge) are
retried twice on a timeout, a connection error, or the answers 429, 502, 503 and
504, after 2 and 5 seconds or the portal's `Retry-After` (at most 10 seconds);
other answers, such as 400, are not retried.  Each check gives up after
2 minutes in total.  The rule is the one of `queries.request_with_retry()`,
which also retries SPARQL queries and the TeX check once (see
[Handlers](handlers.md#database-writes-and-network-requests)).
- **Dependency graph**: whenever a new item's statement references another new item
  (identified by an `Item<n>` placeholder), that dependency is recorded so that items
  can be created in the correct order.

#### Qualifier Merge

Qualifiers are of two kinds:

- **Meaning qualifiers** make a statement what it is: *object has role* (e.g. a
  formula contained as initial condition), *symbol represents* (the quantity of a
  symbol in a defining formula) and *platform* (the software and hardware of a
  workflow usage).  The same subject, property and object with another value of
  these, or without any, is a statement of its own.
- **Additive qualifiers** add information to a statement: assumptions, comments,
  documentation, parameters, years, numbers, and all others.

A `RELATION` entry is the same as a statement on the MaRDI Portal if subject,
property, object and meaning agree.  Then:

| Portal statement | Result |
|---|---|
| has all qualifiers of the entry | skipped (`exists`) |
| lacks some additive qualifiers | only these qualifiers are added to it (`partial`) |
| has another meaning, or none exists | a new statement is written |

Meaning is compared as follows:

- No role matches no role only: a plain *contains F* is written next to *contains F
  as initial condition*.
- A role of the entry that is among the roles of a portal statement matches it: a
  statement *as initial value and parameter* is also the one *as parameter*.
  MaRDMO writes one role per statement and imports such a statement as one
  relation for each role the questionnaire offers.
- *Platform* and *symbol represents* must be the same: software and hardware
  together describe one usage, and its parameters belong to that usage.

Symbols of formulas (*in defining formula*) are compared with the statements of
the same formula or quantity on the MaRDI Portal (`check_symbols()`), since a
symbol stands for exactly one quantity:

| Same symbol on the portal | Result |
|---|---|
| with the same quantity | skipped (`exists`) |
| with another quantity | the export stops: MaRDMO cannot change what the symbol stands for (e.g. a symbol block of a fetched formula deleted and added again with another quantity) |
| without a quantity (no *symbol represents*) | the quantity is added to it (`partial`) |
| none | a new statement is written |

The SPARQL check also finds a portal statement with a role for an entry without
one, so entries of the properties MaRDMO writes with meaning qualifiers
(*contains*, *described by source*, *uses*) are always compared with the portal
statements again.  Several entries adding to the same statement share it; each
qualifier is added once.

### 7. Cyclic Dependency Check

`is_cyclic(dependency)` inspects the dependency graph before proceeding.  If a cycle
is detected an error page is returned.

### 8. OAuth2 Authentication

`post()` serialises the payload and the topological item order into the Django
session and redirects the user to the MaRDI Portal OAuth2 authorisation endpoint.
After the user approves the access, the portal redirects back to the MaRDMO callback
URL.  `callback()` validates the CSRF state token, exchanges the authorisation code
for an access token, and launches the background upload.

### 9. Background Upload

The upload runs in a **daemon thread** so the browser can display a live progress
page immediately.  Progress and results are kept in Django's cache, so the progress
page works regardless of which server process handles the request.  The upload proceeds in two phases:

**Phase 1 — New items** (in topological dependency order):
Each new item is posted to the Wikibase REST API as a single request containing its
label, description, aliases, and **all** its statements at once.  Once the MaRDI
Portal assigns a real QID, every remaining `Item<n>` placeholder in the payload is
replaced with that QID, so subsequent items that depend on it reference the correct
identifier.

**Phase 2 — Relations**:
`RELATION<n>` entries (statements targeting existing items) and `ALIAS<n>` entries
are posted **individually**, one statement per request.  Relations found existing
in step 6 are skipped; for those that only lack qualifiers, the missing
qualifiers are added to the existing statement (a `PATCH` of its qualifiers)
instead of writing it again.

#### Error Handling

The upload layer handles MaRDI Portal communication errors gracefully:

| Condition | Behaviour |
|---|---|
| Timeout / connection error | Retry with exponential back-off (5 attempts in total) |
| HTTP 429 (rate limit) | Wait for the `Retry-After` duration (seconds or HTTP date, at most 60 seconds), then retry |
| HTTP 403 / 5xx | Retry with exponential back-off (5 attempts in total); the portal sometimes answers 403 when it is merely unstable |
| HTTP 422 `item-label-description-duplicate` | Link the conflicting existing item instead of creating a new one and continue; the result page notes that the item's details from the questionnaire were not added to it |
| Any other HTTP 422 | Stop the upload with a plain-language reason (e.g. label and description are identical) |
| Any other HTTP error | Stop the upload with the item or relation concerned and the portal's message |

If the upload stops after something has already been created, everything created
so far is still written back to the RDMO project (step 10) and the result page is
shown with an **Upload incomplete** banner.  Exporting again continues from there
instead of creating the same items twice.

### 10. Success Page and Catalog Update

After all items and relations have been posted, `compare_items()` compares the
initial payload (before upload) with the final payload (after upload, containing real
QIDs) to identify every newly created item.  `replace_ids()` then updates all
matching RDMO project Values in place:

- **Wikidata items**: the `external_id` is updated from `wikidata:<QID>` to
  `mardi:<QID>` and `[wikidata]` is replaced by `[mardi]` in the text field.
- **User-defined items** (`user:<uuid>`, see [Item IDs](ids.md)): ID-question
  Values (where `text` is `"not found"`) are resolved via sibling Name/Description
  Values at the same set index and updated to `mardi:<QID>`; every other Value
  with the item's `user:` ID gets the new ID with them.  Relation Values that
  still store `not found` are matched by their label/description pair.
- **Publications created from a DOI**: their ID question gets the new item, as
  for the other user-defined items.

After the catalog update, a success page is rendered showing the exported data in
two switchable views.  Items that were linked to an existing duplicate instead of
being created are listed in a *Please note* box above the views.

#### List View

All newly created MaRDI Portal items are shown grouped by class (Mathematical Model,
Research Problem, Formula, …, Publication, Author, Journal) in a fixed display order.  Each item is rendered as a
collapsible section showing every statement that was written to the portal as
`property → value` lines.

- **Portal item objects** are shown as clickable blue links to the item's portal page.
- **External identifiers and URLs** (Wikidata QID, DOI, ORCID, swMath work ID,
  MORwiki ID, zbMATH author ID, ISSN, QUDT quantity kind / constant, and plain URLs)
  are resolved to their canonical base URLs and rendered as clickable links.  User-entered
  URLs only become links if they use `http` or `https`; other schemes (e.g. `git://`)
  are shown as text.
- **Quantity values** are displayed as the numeric amount followed by the unit name.
  If the unit is a named portal item it is rendered as a clickable blue link.  The
  dimensionless unit `1` is suppressed.
- **Formulas** stored with the `math` datatype are typeset inline using
  [MathJax](https://www.mathjax.org/) (Apache 2.0).
- **Qualifier statements** are shown indented below their parent statement.
- **Relations to existing items** are shown in a separate section at the bottom.
  A statement that was on the portal already and only got qualifiers is marked
  *(existing statement, qualifiers added:)* and lists only the added qualifiers.

#### Graph View

An interactive network diagram built with
[Cytoscape.js](https://js.cytoscape.org/) (MIT) provides a visual overview of the
exported data.

**Node types:**

| Shape | Colour | Meaning |
|---|---|---|
| Circle | Distinct colour per class | Newly created MaRDI Portal item |
| Circle | Grey | Existing MaRDI Portal item (referenced but not created) |
| Rectangle | Light yellow | Literal value (text, number, URL, …) |

Formulas replace their node label with a rendered MathJax image inside the node
rectangle.

Clicking any circle node opens its MaRDI Portal page in a new tab.  Clicking any
rectangle node that has an associated URL opens the external URL.

**Edges** are directed and labelled with the property name.  Quantity nodes are
connected to their unit via an additional `unit` edge.

**Qualifier tooltip**: clicking an edge opens a floating tooltip listing all qualifier
statements for that edge.

**Zoom and pan**: standard Cytoscape scroll-to-zoom and drag-to-pan apply.  The fit
button resets the viewport to show all nodes.

#### Filter Panel

A collapsible *Filter* panel on the graph view lets users reduce visual noise:

- **Legend (class toggles)**: clicking a class label dims it and hides all nodes of
  that class together with their edges.
- **Node-type toggles**: separate *Hide literal nodes* and *Hide existing items*
  checkboxes toggle those entire node layers.
- **Property checklist**: each distinct edge-label has a checkbox; unchecking a
  property hides all edges with that label.  Literal nodes that become fully
  disconnected are automatically hidden.

All filter dimensions compose: the effective visibility of any node or edge is the
intersection of all active filters.
