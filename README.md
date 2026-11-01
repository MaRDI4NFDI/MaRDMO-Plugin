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

Run Django scripts with the RDMO app, e.g.

    cd ~/Work/test/rdmorganiser/rdmo-app
    env/bin/python manage.py shell < ~/Work/MaRDMO-Plugin/dev-tests/<script>.py
