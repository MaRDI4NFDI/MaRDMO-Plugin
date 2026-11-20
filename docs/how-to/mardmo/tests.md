# Run and Update the Tests

The tests run offline: the network is blocked (pytest-socket), and the
answers of the MaRDI Portal, Wikidata and the citation services come from
recordings in `tests/data/recorded`.  CI runs exactly the same tests.

## Run the tests

```bash
pip install -e ".[test]"
QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest
```

`QUESTIONNAIRE` is the `catalog` folder of a MaRDMO-Questionnaire checkout.
The tests in `tests/db` import it into the test database once per run, as an
admin would import it; other tests compare the plugin with it.  Without
`QUESTIONNAIRE`, these tests are skipped locally (in CI they fail instead).

| Folder | What it tests |
|---|---|
| `tests/static` | files only: data files, SPARQL queries, templates, workflows, README, questionnaire |
| `tests/unit` | single functions, without database |
| `tests/db` | with a database and the questionnaire: providers, handlers, hydration, preview, export |
| `tests/browser` | pages in a real browser (opt-in locally, see [Browser tests](#browser-tests-pages-in-a-real-browser)) |
| `tests/live` | the recordings against the real portal (opt-in, see [Live check](#live-check-does-the-portal-still-answer-as-recorded)) |
| `tests/support` | helpers, no tests: reading pages (`html.py`), recordings, the providers' calls |

Every test starts in English with an empty cache (`tests/conftest.py`), so
a test does not depend on the language or the answers of the tests before.

### Reading a page in a test

A test checks what the user sees, not the exact markup, so a change of the
look does not break it.  `tests/support/html.py` parses a page and finds its
parts by ID, class or tag:

```python
from tests.support.html import element, export_button, links, preview_page, text

page = preview_page(client, documentation)          # GET the export page; language='de'
assert export_button(page) == 'disabled'
problems = element(page, id='export-problems')
assert 'Missing Short Description' in text(problems)
assert ('To interview', f'/projects/{documentation.pk}/interview/12/') in links(problems)
```

`rendered_preview(project)` renders the catalog's template without request
and checks.  Compare HTML literally only where the markup itself is tested
(e.g. `PageRef` in `tests/unit/test_pages.py`).

## Run them on PostgreSQL or MariaDB

SQLite in memory is the default.  `TEST_DB=postgresql` or `TEST_DB=mysql`
(MySQL or MariaDB) runs the tests on a local server, reached by its Unix
socket as the user running the tests.  pytest-django creates the test
database `test_mardmo_tests` and drops it afterwards.

```bash
TEST_DB=postgresql QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest
TEST_DB=mysql QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest
```

The drivers are those of RDMO's extras (`pip install "rdmo[postgres]"` or
`"rdmo[mysql]"`); for MariaDB, PyMySQL works too and needs no compiler.  The
user needs, once:

- **PostgreSQL:** permission to create databases:
  `sudo -u postgres createuser --createdb <user>`
- **MariaDB:** a login by socket and rights on the test database:

  ```bash
  sudo mariadb -e "CREATE USER IF NOT EXISTS '<user>'@'localhost' IDENTIFIED VIA unix_socket;
    GRANT ALL PRIVILEGES ON \`test_mardmo_tests\`.* TO '<user>'@'localhost';"
  ```

`TEST_DB_USER`, `TEST_DB_PASSWORD`, `TEST_DB_HOST` and `TEST_DB_PORT` connect
to another server; a server reached by TCP must be allowed with
`--allow-hosts` (CI does this for its database containers).

## What runs in CI

`tests.yml` runs ruff, the tests with coverage, and builds the package.  The
tests use the MaRDMO-Questionnaire branch with the same name as the plugin
branch; without one, the questionnaire branch of the integration branch the
plugin branch shares commits with that `main` has not (e.g. `0.8.0`; also
when the branch goes on after its pull request was merged), else `main`.  A plugin change that
needs a questionnaire change gets a questionnaire branch of the same name.

| Event | Combinations |
|---|---|
| Push to any branch | Python 3.14, RDMO 2.5.2, SQLite |
| Pull request to `main` or the integration branch, release | Python 3.10, 3.13, 3.14 × RDMO 2.5.1, 2.5.2 on SQLite; Python 3.14, RDMO 2.5.2 on PostgreSQL 16 and on MariaDB 11; the browser tests on Python 3.14, RDMO 2.5.2, SQLite |

A test of the database jobs fails if the tests did not run on the database
asked for, so a database job cannot pass on SQLite unnoticed.

Every job fails if the coverage falls below `fail_under` in `pyproject.toml`
(89 %; 91 % were reached).  Raise the floor when the coverage rises; never
lower it to make a pull request pass.  Locally:
`coverage run -m pytest && coverage report`.

Besides, `live-check.yml` checks the MaRDI Portal and Wikidata every night
(see [Live check](#live-check-does-the-portal-still-answer-as-recorded)).

## Golden files: when the export changes

`tests/db/test_export.py` builds the export of fixed projects, as it would be
handed to the upload, and compares the check messages, the payload and the
written items with `tests/data/golden/<project>.json`.  A failing test lists
what changed, e.g.
`/payload/Item0000000058/description: '' -> 'No Description Provided!'`.

After an intended change of the export, write the files again and review
their diff in the pull request like code:

```bash
GOLDEN=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest tests/db/test_export.py
```

The order of the writes is not stored: items that do not need each other come
in any order.  The test checks instead that every item comes after the items
it needs.

To review a golden file (or its change), read it as text: every item the
export creates with its statements, the statements it adds to portal items,
and the aliases:

```bash
python -m tools.synthetic.summary synthetic_model > synthetic_model.md
```

## Cycles of new items: the order of creation

The export creates new items after the items they refer to and breaks cycles
(see the export pipeline, *Order of Creation*).  Three kinds of tests check it:

| Test | Checks |
|---|---|
| `tests/unit/test_cycles.py` | hand-made cases and seeded random graphs of up to 1000 items and 10000 references: no cycle left, every item after the items it refers to, every statement arrives exactly once (in its item or afterwards), only statements that closed a cycle come afterwards, the same result for every order of the items, and the time |
| `tests/db/test_upload.py` | for every project of `tests/data/projects`: every reference of a new item (also in qualifiers) is a dependency, and the real upload (`_background_post`) against a fake portal that rejects any `Item…` placeholder left writes every statement |
| `tests/unit/test_cycles_real.py` | the checks of `test_cycles` on the relation graphs of real portal models, algorithms and the workflow, every item made new (`tests/data/cycles`, written by `dev-tests/cycles_real.py`, which hydrates them read-only from the portal) |

## Red marks: the preview shows the problems of the checks

`tests/db/test_marks.py` deletes (and blanks) one answer of every question of a
project of each catalog, one at a time, and renders the preview: every problem
of the checks must be red on its page, and nothing else may be red.  It fails
when a template marks something itself (only `{% marks %}` and
`{% remaining_marks %}` may), or when a check problem cannot be shown.  A
failure names the answer, the page and the message, e.g.
`delete quantity/name: page-quantity-1: not shown: Missing Name`.  With the
[synthetic documentations](#synthetic-documentations-every-question-option-and-relation)
every question of each catalog is deleted once.  white_2006 runs once more in
German; there a problem whose section has no German name fails as well (see [How to Translate MaRDMO](translate.md)).

## Synthetic documentations: every question, option and relation

`tests/data/projects/synthetic_*.xml` are one documentation per catalog
(model, model basics, algorithm, workflow) that use everything the catalog
has: every question, every fixed option (relation types, properties,
reproducibility, data set sizes, ...), options with their text, and in every
dropdown of items an item of each source it offers: own new items, items of
the MaRDI Portal, of Wikidata, and new items typed into a relation (MaRDMO
gives them a page).  Each section has two or more new items, a portal item
and a Wikidata item as page items (MaRDMO fills their pages and adds the
pages of their relations), and new publications whose citation the preview
looks up (Crossref, DataCite, ORCID, zbMATH).

They are made by a generator, not by hand: `tools/synthetic/<catalog>.py`
describes the documentation, `tools/synthetic/writer.py` writes it as the
interview does (each answer where the interview puts it, validated, saved,
announced with RDMO's `value_created`, so MaRDMO's handlers run; items are
selected from the options their dropdown offers).  Then the preview runs as
the user opens it: items on the portal already are reused ("Use this item"),
and nothing may be left that prevents the export.  `tools/synthetic/complete.py`
answers what MaRDMO asks of the pages of created items it filled (Wikidata
items with name and description only, items typed into a relation) before
that; pages of portal items keep their gaps, which are hints (#167).

| Test | What it checks |
|---|---|
| `tests/static/test_synthetic.py` | every question answered, every option chosen, options with text used with a text, every source of every dropdown (exceptions with reason in `UNAVAILABLE`); every relation of the documentation is a statement of the export, in the direction MaRDMO's `get_relations()` gives |
| `tests/db/test_export.py` | the export as stored (golden files), as for every project in `tests/data/projects` |
| `tests/db/test_synthetic_preview.py` | the preview as the user opens it: every page shown, the citations of the new publications looked up (recorded `preview_synthetic_*`), nothing that prevents the export |
| `tests/db/test_marks.py` | the red marks and the blue hints, for every question |

### Build them again

When the questionnaire gets a question or option, `test_synthetic.py` names
it: add it to the description and build again.  The build asks the MaRDI
Portal, Wikidata and the citation services (read-only, a pause before each
request; a few hundred requests per documentation):

```bash
BUILD=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog \
    pytest tests/db/test_synthetic_build.py --force-enable-socket -s -k synthetic_model
RECORD=1 GOLDEN=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog \
    pytest tests/db/test_export.py tests/db/test_synthetic_preview.py --force-enable-socket -k synthetic_model
```

The new items get IDs from the documentation's name and a counter, so the
same description and portal data give the same XML.  A build stops with what
is wrong: an item the dropdown does not offer (the error lists what it
offers), an answer stored twice, a check problem (`BUILD_PAGES=1` lists the
pages of the sections concerned), an item on the portal that cannot be
reused, or an internal error of the export.  Things learned:

- New items may need each other both ways: the export breaks such cycles
  (#164).  The synthetic documentations have some on purpose (formulas,
  quantities, tasks, models, algorithms); relations stored on the other item
  ("approximates" is stored as "approximated by" there, see `get_relations()`)
  close them.
- Choose Wikidata items without a twin on the portal and without a long chain
  of defining formulas (MaRDMO adds a page for every quantity of a Wikidata
  formula, recursively).
- New publications need DOIs that are on neither the portal nor Wikidata
  (recent ones); otherwise the dropdown offers that item.  The descriptions
  select publications by their DOI (`Doi('10.…', 'mardi:Q…')`, or without an
  item for a new one), as the user types it.

## Recordings: when the requests change

A test that sends a request that is not recorded fails, also where MaRDMO
catches the error.  Every test starts with an empty cache, so it sends (and
records) all its requests itself, whichever tests ran before.  Record again when a test is new, when MaRDMO sends other
requests, or when the portal data changed.  Recording only reads, with a
pause before every request:

```bash
RECORD=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest --force-enable-socket tests/db/test_hydration.py
RECORD=1 GOLDEN=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest --force-enable-socket tests/db/test_export.py
```

Recording replaces the recordings the tests use.  `RECORD=missing` (with
`--force-enable-socket`) replays instead and sends only the requests a
recording does not have, adding them to it (the last recording a test
names): for a change that asks a little more, without recording everything
again.  When portal data changed,
also check the expected pages in `tests/db/test_hydration.py` (`PAGES`) and
the diff of the golden files: they show what changed on the portal.

A test can combine recordings, e.g. `portal('si_model', 'export_portal_si_model')`:
it is answered from all of them, and recording stores only the requests the
earlier ones do not have, in the last one.  So the export of a portal item
reuses the requests of its hydration.

## Live check: does the portal still answer as recorded?

Every night, `.github/workflows/live-check.yml` sends every recorded request
again to the MaRDI Portal and Wikidata (one per second, about four minutes)
and runs the dropdown searches live (`tests/live/test_portal.py`).  It
compares the answers by structure, not by value, so ordinary edits on the
portal do not count: the same status code, the keys of every recorded
object, lists with entries (search hits, SPARQL rows) that still have
entries, the same SPARQL result variables and the same TeX check results.
Only reading requests are sent (searches, SPARQL queries, TeX checks); a
recording keeps each request as sent for this.

The live check is not required for pull requests.  A failure opens an issue
"Live check failed" with what changed, or comments on the open one; a
recorded error that now succeeds (the portal fixed it) is a note in the
run's summary.  When the data changed, record again (above); when the API
changed, adapt MaRDMO.  To run it locally:

```bash
LIVE=1 pytest tests/live --force-enable-socket
```

Scheduled workflows run on the default branch only; GitHub turns the
schedule off after 60 days without commits (it says so by email), and a run
started by hand ("Run workflow") turns it on again.

## Browser tests: pages in a real browser

`tests/browser` opens MaRDMO's pages in Chromium (Playwright): what only a
browser shows, i.e. what CSS and JavaScript do.

| File | Page |
|---|---|
| `test_dropdown.py` | a dropdown of RDMO's interview: source badge, label and description in the open list, not the plain text (fails if RDMO stops rendering an option's help as HTML); the stored answer and the filled field plain |
| `test_duplicates.py` | the preview's box "Before you export": the items already on the MaRDI Portal, the decision ("Use this item", "Redefine", the **i**), "Apply" |
| `test_formulas.py` | formulas in the preview rendered by MathJax; one it cannot render shown as TeX |
| `test_math_preview.py` | the formula and symbol questions of RDMO's interview: the TeX typed rendered below the field (also with a TeX extension MathJax loads on demand), the portal's verdict (answered by the browser): its message, the checker's form for a shorthand such as `\R`, nothing without a verdict; MathJax's message for TeX it cannot render; no error while typing, the error after a pause or on leaving the field, no request per key; nothing for other questions |
| `test_progress.py` | the progress page following an upload (`progress.js`, also in German, errors as text), the result page and its graph (cytoscape: nodes, filters, fullscreen), someone else's job |

The pages come from a live server on the test database; the portal and the
upload are faked (the progress tests write what the upload's thread writes).
RDMO's interview sends several requests at once, which would share the
test's database connection in parallel threads: interview tests use
`interview_as`, whose server (`OneRequestAtATime`) answers one request after
another and closes each connection.
Locally they are opt-in:

```bash
pip install -e ".[test,browser]" && playwright install chromium
BROWSER=1 pytest tests/browser --allow-hosts=127.0.0.1,::1,localhost
```

`--allow-hosts` lets the tests reach the local test server, nothing else.
`SCREENSHOTS=<folder>` saves pictures of what the tests look at.  In CI they
run for every pull request and release (see [What runs in CI](#what-runs-in-ci)),
and the pictures are uploaded as the artifact *screenshots* of the run, to
look at the pages of a pull request without running it.  The result graph
is reachable for the tests as `window.mardmoGraph`.

## Add a documentation as a test project

An RDMO project export (XML) of a documentation made with MaRDMO becomes a
golden test.  Add one when it covers something the others do not (another
catalog, other kinds of formulas, conditions or relations); similar projects
add test time and data, but no coverage.

1. Copy the XML to `tests/data/projects/<name>.xml`.  A documentation made with
   a MaRDMO before 0.8.0 has `not found` as the ID of its new items: convert its
   copy to item IDs first (relations then name the ID of their item's page):
   `PYTHONPATH=. python dev-tests/convert_old_project.py ../MaRDMO-Questionnaire/catalog tests/data/projects/<name>.xml`.
2. Record its export requests and write its golden file:
   `RECORD=1 GOLDEN=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest --force-enable-socket tests/db/test_export.py -k <name>`
3. Review `tests/data/golden/<name>.json`: the check messages should be empty
   and the new items and statements as documented.
4. Commit the XML, `tests/data/recorded/export_<name>.json` and the golden file.

The copy is frozen: a later change of the documentation reaches the test only
when the XML is copied again and the golden file written again.
