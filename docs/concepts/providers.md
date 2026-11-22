# Dynamic Optionset Providers

Many questionnaire fields in MaRDMO require the user to reference an external entity — a piece of software, a mathematical model, an algorithm, a research problem, and so on.  These fields are backed by *dynamic optionset providers*: Python classes that the RDMO frontend calls whenever the user types into an autocomplete widget, returning a ranked list of matching items from external knowledge bases or from the current project.

## One Provider, One Table

Every option set of the questionnaire names its provider by a key (`provider_key`), and RDMO creates the provider from the setting `OPTIONSET_PROVIDERS` as `Class(key, label, class_name)`.  It asks the provider for options with the search text only — not with the question — so a provider cannot tell which question it serves; it knows its key.  MaRDMO therefore has one provider class, `MaRDMO.providers.MaRDMOProvider`, and a table in `MaRDMO.optionsets` with one row per key:

```python
'RelatedQuantityWithoutCreation': Search('Options for related Quantities without Creation',
                                         'quantity', answers=['quantity'], sources=['mardi']),
```

A row names the item class (or classes) of the MaRDI Portal search, the questionnaire sections whose items of the user's own are offered too, whether a new item may be created, the sources, whether "new item" is offered, whether RDMO reloads the page after a selection (`refresh`), and from how many characters the search starts.  A new option set needs one row.

`MaRDMO.optionsets.OPTIONSET_PROVIDERS` is the setting for all rows, so an RDMO installation adds it with one line (see the installation instructions).  Up to MaRDMO 0.6 every key had a class of its own (`MaRDMO.model.providers.MathematicalModel` and so on); settings that still list these must be replaced by that line.  Providers of programming languages and software search from the first character, since some of their names have only one (C, R); all others start at three, since a single letter matches hundreds of items and slows the search.

## Three Provider Tiers

Providers are organised into three tiers of increasing capability.

### Tier 1 — Pure search

The provider of publications is different (`Search.by_identifier`, #158): it searches by the identifier the user types with its prefix (`doi:10.…`), not by a title, and offers one publication: the portal's, else Wikidata's, else the DOI itself as a new one (see [Publications](publication.md)).  A text without prefix offers nothing.

The simplest providers query the **MaRDI Portal**, or the **MaRDI Portal and Wikidata**, and return the matching items of the kind the question asks for (see below).  A "new item" option is included in the ID dropdowns of pages, so the user can add an own item when no appropriate one exists.

### Tier 2 — Search + project items

Tier 2 providers extend Tier 1 by also surfacing items the user has already defined or selected elsewhere in the **current RDMO project**.  This lets a user re-reference an entity they documented in an earlier section without having to look it up again.  An item of the project is offered with the ID of its page, so the relation refers to that page (see [Item IDs](ids.md)).

### Tier 3 — Search + project items + inline creation

The most capable providers add the ability to **create a new item on the fly**.  The user types a label and the provider offers it as a new item; the typed text is the label, as typed.  Selecting it gives the answer a new `user:` ID; where the catalog has a section for the item, MaRDMO creates its page with the same ID and the typed name (the short description is entered there), otherwise MaRDMO adds a generic description (see [Item IDs](ids.md)), and the item is created on the MaRDI Portal during export.  Every option in the open dropdown shows a coloured badge with its source, the label in bold and the description in grey italics on a second line (#142; the option's `help`, `MaRDMO.queries.option_help`): **mardi** for a MaRDI Portal result, **wikidata** for a Wikidata result, **project** for an item of the project, and **new** for a typed new item or a new publication; the "new item" option of an ID dropdown has none.  RDMO renders an option's text and then its help as HTML; a CSS rule in the help hides the text of laid-out options (a browser without `:has()` shows both).  The option's text stays `Euler method (numerical ODE solver)`: it is what RDMO stores in the answer and shows in the filled field, what the dropdown searches with when it is opened again, and what screen readers announce.  The layout is only in the open dropdown; the preview shows the source by the ID.  Showing it in the filled field too would need RDMO to ask the provider for a stored answer's option, as it does for default values; storing the layout as HTML was rejected (RDMO's own views and exports would show the markup).

## MaRDI Portal vs Wikidata Search

A dropdown offers only items of the kind its question asks for (#170), from both sources, but they are restricted differently.

**MaRDI Portal: by profile or class.**  Most item classes have a *MaRDI profile* (`MaRDMO.optionsets.PROFILES`: the software profile for software, the model profile for models, …).  Many portal items have the profile but no class (*instance of*): most software, R and Julia packages, some algorithms.  So a class with a profile is searched by its profile, as the portal's own search does; the curated items (MathModDB, MathAlgoDB) all have it.  The portal does not index the values of the profile type for `haswbstatement`, so the search uses the portal's faceted search (`haswbfacet`), which finds the profile pages; each names its item.  The classes without a profile (benchmark, programming language, computer hardware, CPU model, method, research tool, process step) are searched by class.  A dropdown of classes of both kinds sends both searches in parallel; it does not search Wikidata, so it sends two requests, as the others do.  The formula profile includes the formulas of the Digital Library of Mathematical Functions.

A profile can belong to several classes: algorithmic and computational tasks share the task profile, quantities and quantity kinds the quantity profile.  A dropdown of one of them leaves out the items of the other class (`Search.excluded_classes`); an item with the profile but no class is offered in both.

**Wikidata: by root classes.**  Each item class has Wikidata *root classes* (`MaRDMO.optionsets.WIKIDATA_ROOTS`, e.g. `software` (Q7397) for software).  A Wikidata hit is offered if it is an instance or a subclass of something at or below one of them; the path is walked upwards from the item's classes, since a broad root such as software has thousands of subclasses.  Many items are classes themselves (an equation, a model type), so *subclass of* counts as well as *instance of*.  Three kinds of item are handled differently:

- **Process steps** are not searched on Wikidata (`NO_WIKIDATA`): it has nothing for them.
- **Research problems** are phenomena, processes and the like; no Wikidata class fits them (`NOISE_FILTERED`).  Their hits are filtered the other way round: an item that is an instance of a class of `WIKIDATA_NOISE` or of a subclass (persons, taxa, writings, films, places, organizations, …) is left out, the rest is offered.  The classes are narrow on purpose; a broad one would leave out real research problems.
- **Computational tasks and research workflows** have roots although Wikidata has hardly any items of them yet: if it gets some, they are offered without a change to MaRDMO.

The check (`MaRDMO.class_check.wikidata_matches`) is one SPARQL query for all hits of a search.  It asks QLever's Wikidata endpoint (University of Freiburg, updated live), which answers in a fraction of a second, and Wikidata's own endpoint if QLever fails.  Wikidata's main endpoint does not have the scholarly articles (they are in a graph of their own); there an item it does not know counts as noise.  If both fail, the first ten hits are offered unfiltered, as before the check.

A new item class needs its roots in `WIKIDATA_ROOTS` (or an entry in `NO_WIKIDATA` or `NOISE_FILTERED`), else a test fails (`tests/unit/test_wikidata_roots.py`), and its profile in `PROFILES` if it has one.

## Typing an item's ID

If the item a user wants is not among the results, the user can type its ID with the prefix of its source: `mardi:Q123` or `wikidata:Q42` (the prefix in any case, spaces around the colon allowed).  The dropdown then offers only that item, if it fits the dropdown as a search hit would: on the portal of one of its classes or with one of its profiles (and not of a class it leaves out), on Wikidata at or below its roots (or not noise).  Neither "new item" nor the typed text as an item to create is offered.  A merged item is offered as the one it was merged into; an ID that does not exist, or of a source the dropdown does not search, offers nothing.

## Autocomplete Mechanism

The following steps happen each time the user types in an autocomplete field:

1. **Debounced request** — after a short pause the browser sends an HTTP request to the Django backend, passing the current search term.

2. **`query_api_per_class`** — the backend fires a [CirrusSearch](https://www.mediawiki.org/wiki/Help:CirrusSearch) query against the MediaWiki API.  CirrusSearch is the Elasticsearch-backed full-text search engine embedded in Wikibase/MediaWiki.  The `haswbstatement` keyword is a CirrusSearch extension that filters results to items carrying a specific property-value pair:

    ```
    GET /w/api.php
      ?action=query
      &list=search
      &srsearch=euler* haswbstatement:P31=Q68663
      &format=json
    ```

    Here `P31` is the *instance of* property and `Q68663` is the item class QID (e.g. *mathematical model*).  The trailing `*` enables prefix matching so partial input is handled gracefully.  This is the search of the classes without a profile; a class with a profile is searched on the profile pages (namespace 0), which name their items, in the same request:

    ```
    GET /w/api.php
      ?action=query
      &generator=search
      &gsrsearch=lme4* haswbfacet:P1460=Q5976450
      &gsrnamespace=0
      &prop=pageprops
      &ppprop=wikibase_item
      &format=json
    ```

    `P1460` is the *MaRDI profile type*, `Q5976450` the software profile; several profiles are separated by spaces (alternatives).  On Wikidata, the label search (`wbsearchentities`) asks for 50 hits; the class check leaves out most of them.

3. **`wbgetentities` follow-up** — the QIDs returned by the search are resolved to English labels and descriptions via a second API call (with their classes too where a shared profile leaves out the other class):

    ```
    GET /w/api.php
      ?action=wbgetentities
      &ids=Q42|Q137|Q951
      &props=labels|descriptions
      &languages=en
      &format=json
    ```

4. **Cache** — the results of each source (MaRDI Portal, Wikidata) are kept in Django's cache for five minutes, keyed by search text and item class.  Repeated searches — while typing, or for the same entity type on another page — are then answered without querying the portal again.  Each request is given up after five seconds (`SEARCH_TIMEOUT`); a quick failure (a connection error, or the answer 429, 502, 503 or 504) is retried once after half a second, a timeout is not, so a search never keeps an RDMO worker much longer than one request.  Failed requests are not cached, so the next search tries again.  The results do not depend on the project, so the user's own answers cannot make them outdated.  The Wikidata search is shared by all dropdowns; each filters it by its classes, in parallel with the portal search.  The class check's answers are cached per item and set of classes for a day, so an item found again is not checked again.

5. **Duplicates** — a Wikidata result with the same label (ignoring case) and the same description as a MaRDI Portal result is left out: it is the same item, and the export would ask the user to select the MaRDI Portal one.  Results without a description are never merged, since a label alone does not make two items the same.

6. **Merge and return** — for Tier 2 and 3 providers, the matching items the user has already entered in the project are put before the external results, and the list is returned to the autocomplete widget.  These project items are read from the database on every request (two queries, regardless of how many entity types the provider covers), so an item saved a moment ago is offered right away.
