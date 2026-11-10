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

The simplest providers query the **MaRDI Portal**, or the **MaRDI Portal and Wikidata**, and return whatever matches.  A "new item" option is included in the ID dropdowns of pages, so the user can add an own item when no appropriate one exists.

### Tier 2 — Search + project items

Tier 2 providers extend Tier 1 by also surfacing items the user has already defined or selected elsewhere in the **current RDMO project**.  This lets a user re-reference an entity they documented in an earlier section without having to look it up again.  An item of the project is offered with the ID of its page, so the relation refers to that page (see [Item IDs](ids.md)).

### Tier 3 — Search + project items + inline creation

The most capable providers add the ability to **create a new item on the fly**.  The user types a label and the provider offers it as a new item; the typed text is the label, as typed.  Selecting it gives the answer a new `user:` ID; where the catalog has a section for the item, MaRDMO creates its page with the same ID and the typed name (the short description is entered there), otherwise MaRDMO adds a generic description (see [Item IDs](ids.md)), and the item is created on the MaRDI Portal during export.  Every option shows its source as a grey tag in the open dropdown (the option's `help`, `MaRDMO.ids.source_help`): **[mardi]** for a MaRDI Portal result, **[wikidata]** for a Wikidata result, **[project]** for an item of the project, and **[new]** for the typed new item; the "new item" option of an ID dropdown has none.  The tag is not part of the option's text (`Euler method (numerical ODE solver)`), so it is not stored in the answer: a filled-in field shows the label and description, the preview shows the source by the ID.

## MaRDI Portal vs Wikidata Search

For the **MaRDI Portal**, providers use a class-restricted search: only items that are an *instance of* the relevant item class are returned.  For **Wikidata**, an **unrestricted** search is used instead — equivalent to typing a term directly into the Wikidata search bar.  The reason for this asymmetry is that Wikidata's class hierarchy is too heterogeneous for reliable filtering: a piece of software might be `instance of free software` rather than `instance of software`, making a class-restricted query miss many valid results.

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

    Here `P31` is the *instance of* property and `Q68663` is the item class QID (e.g. *mathematical model*).  The trailing `*` enables prefix matching so partial input is handled gracefully.

3. **`wbgetentities` follow-up** — the QIDs returned by the search are resolved to English labels and descriptions via a second API call:

    ```
    GET /w/api.php
      ?action=wbgetentities
      &ids=Q42|Q137|Q951
      &props=labels|descriptions
      &languages=en
      &format=json
    ```

4. **Cache** — the results of each source (MaRDI Portal, Wikidata) are kept in Django's cache for five minutes, keyed by search text and item class.  Repeated searches — while typing, or for the same entity type on another page — are then answered without querying the portal again.  Failed requests are not cached, so the next search tries again.  The results do not depend on the project, so the user's own answers cannot make them outdated.

5. **Duplicates** — a Wikidata result with the same label (ignoring case) and the same description as a MaRDI Portal result is left out: it is the same item, and the export would ask the user to select the MaRDI Portal one.  Results without a description are never merged, since a label alone does not make two items the same.

6. **Merge and return** — for Tier 2 and 3 providers, the matching items the user has already entered in the project are put before the external results, and the list is returned to the autocomplete widget.  These project items are read from the database on every request (two queries, regardless of how many entity types the provider covers), so an item saved a moment ago is offered right away.
