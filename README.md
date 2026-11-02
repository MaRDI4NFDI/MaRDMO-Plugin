# MaRDMO dev tests

Manual checks before a release.  This folder is a git worktree of the orphan
branch `dev-tests`, which holds only these scripts; the code branches ignore it
through `.git/info/exclude` (it was set up with
`git worktree add --orphan -b dev-tests dev-tests`).  Results go to `results/`,
which is not committed.

The scripts check the code in the main worktree (`../MaRDMO`), whichever
branch is checked out there.

Rules for every script:

- Read-only towards the MaRDI Portal and Wikidata: no script posts anything.
- Temporary RDMO projects are created with a `TEMP` title and deleted at the end.
- Paths come from environment variables, with the local paths as defaults.

| Script | Checks | Needs |
|---|---|---|
| `static_attributes.py` | attribute and option URIs used by the code exist in the questionnaire XML (`QUESTIONNAIRE`, default `~/Work/MaRDMO-Questionnaire/catalog`) | nothing |
| `idempotence.py` | selecting an item twice changes nothing; a relatant deleted by hand comes back on re-selection; filling items in reverse order gives the same content (items from `items.json`; `TYPES`, `LIMIT`, `CASES`, `GROUPS`, `OUT`) | RDMO app, portal read access |
| `deletion.py` | deleting one set per section the way RDMO's `delete_set` does removes exactly that set (sections with 12+ sets lose set 1, so sets 10-19 show collateral loss); checks, export and preview still run; re-selecting the main item brings the items back (`ITEMS`, e.g. `model_all` for every model in `items.json`; `QUICK=1`; `RDMO_FILTER_SET=fixed` to patch RDMO's prefix bug in-process; `OUT`) | RDMO app, portal read access |
| `roundtrip_collect.py` | round trip portal item → project → export payload: saves answers, check messages and the payload (built also when the checks fail, nothing is posted) per item for offline comparison; an unchanged item should give no new items and only statements that already exist (`TYPE`, `ITEMS`, e.g. `model_all` or `algorithm_all`; `QIDS`; `LIMIT`; `OUT`) | RDMO app, portal read access |
| `preview_payload.py` | renders the preview as on the export page, then builds the export payload of the same project (nothing is posted); saves both per item for `preview_compare.py` (`TYPE`, `ITEMS`, `QIDS`, `LIMIT`, `MOCK=1` for the workflow with the mock usages of `workflow_mock.py`, `OUT`) | RDMO app, portal read access |
| `preview_compare.py` | offline: parses the saved previews and compares them with the payloads in both directions — items, relations (with the expected property, direction and role per relation label), assumptions, formulas, formula elements, aliases, literals and qualifiers (`python3 preview_compare.py results/preview-model ...`) | nothing |
| `workflow_mock.py` | workflow Q6032641 with mock algorithm and method usages added to its process steps: selecting twice, a usage gained on the portal, a usage set deleted by hand, order of process steps; every usage set must hold exactly one usage | RDMO app, portal read access |

`common.py` holds the helpers the scripts share (selecting an item the way the
interview does, dumping values, comparing content without set numbers).

`items.json` holds the test items per type: MaRDI models and algorithms and
Wikidata models, picked evenly by number of statements, every model and every
algorithm on the portal (`model_all`, `algorithm_all`; items with the MaRDI
model or algorithm profile), and the one MaRDMO workflow on the portal (Q6032641; the other items with the workflow profile are
script-based workflows created elsewhere).

Run Django scripts with the RDMO app, e.g.

    cd ~/Work/test/rdmorganiser/rdmo-app
    env/bin/python manage.py shell < ~/Work/MaRDMO-Plugin/dev-tests/<script>.py
