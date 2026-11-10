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
plugin branch is based on (e.g. `0.8.0`), else `main`.  A plugin change that
needs a questionnaire change gets a questionnaire branch of the same name.

| Event | Combinations |
|---|---|
| Push to any branch | Python 3.14, RDMO 2.5.2, SQLite |
| Pull request to `main` or the integration branch, release | Python 3.10, 3.13, 3.14 × RDMO 2.5.1, 2.5.2 on SQLite; Python 3.14, RDMO 2.5.2 on PostgreSQL 16 and on MariaDB 11 |

A test of the database jobs fails if the tests did not run on the database
asked for, so a database job cannot pass on SQLite unnoticed.

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

Recording replaces the recordings the tests use.  When portal data changed,
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

## Add a documentation as a test project

An RDMO project export (XML) of a documentation made with MaRDMO becomes a
golden test.  Add one when it covers something the others do not (another
catalog, other kinds of formulas, conditions or relations); similar projects
add test time and data, but no coverage.

1. Copy the XML to `tests/data/projects/<name>.xml`.
2. Record its export requests and write its golden file:
   `RECORD=1 GOLDEN=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog pytest --force-enable-socket tests/db/test_export.py -k <name>`
3. Review `tests/data/golden/<name>.json`: the check messages should be empty
   and the new items and statements as documented.
4. Commit the XML, `tests/data/recorded/export_<name>.json` and the golden file.

The copy is frozen: a later change of the documentation reaches the test only
when the XML is copied again and the golden file written again.
