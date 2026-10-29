# Dynamic Optionset Providers

Many questionnaire fields in MaRDMO require the user to reference an external entity — a piece of software, a mathematical model, an algorithm, a research problem, and so on.  These fields are backed by *dynamic optionset providers*: Python classes that the RDMO frontend calls whenever the user types into an autocomplete widget, returning a ranked list of matching items from external knowledge bases or from the current project.

## Three Provider Tiers

Providers are organised into three tiers of increasing capability.

### Tier 1 — Pure search

The simplest providers query the **MaRDI Portal**, or the **MaRDI Portal and Wikidata**, and return whatever matches.  A "not found" option is sometimes included so the user can explicitly signal that no appropriate item exists.

### Tier 2 — Search + project items

Tier 2 providers extend Tier 1 by also surfacing items the user has already defined or selected elsewhere in the **current RDMO project**.  This lets a user re-reference an entity they documented in an earlier section without having to look it up again.

### Tier 3 — Search + project items + inline creation

The most capable providers add the ability to **create a new item on the fly**.  The user types a plain-text label and a short description — the same two pieces of information that a result returned from an external source would carry — and the provider wraps this in a special option that later triggers item creation in the MaRDI Portal during export.  Items entered this way are visually distinguishable from portal or Wikidata results by the absence of a source tag: a portal result appears as `Euler method (numerical ODE solver) [mardi]`, a Wikidata result as `Euler method (numerical ODE solver) [wikidata]`, while an inline-created item appears as `My solver (custom ODE solver)` with no tag.

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

5. **Merge and return** — for Tier 2 and 3 providers, the matching items the user has already entered in the project are put before the external results, and the list is returned to the autocomplete widget.  These project items are read from the database on every request (two queries, regardless of how many entity types the provider covers), so an item saved a moment ago is offered right away.
