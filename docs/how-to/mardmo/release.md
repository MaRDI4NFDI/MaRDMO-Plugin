# Make a Release

A release puts a new MaRDMO version on PyPI and archives it on Zenodo.  It
starts with pushing a tag; the workflow `pypi-publish.yml` does the rest and
publishes the GitHub release last, so Zenodo (which archives every published
release) never archives a version that did not reach PyPI.

## Before the release

- **Manual checks:** the scripts of the `dev-tests` branch (see its README),
  read-only against the MaRDI Portal.
- **Questionnaire:** the MaRDMO-Questionnaire has its own version numbers.  If
  this MaRDMO version needs questionnaire changes, release the questionnaire
  first and name the MaRDMO version it is meant for in its description.  The
  release workflow tests against the questionnaire's latest release, so a
  missing questionnaire release stops the MaRDMO release before anything is
  published.  A MaRDMO version without questionnaire changes needs no new
  questionnaire release.

## Release

1. **Version bump:** a pull request that changes only `__version__` in
   `MaRDMO/__init__.py` (`pyproject.toml` reads it from there); merge it when
   the tests pass.
2. **Update the local main:** `git checkout main && git pull`, so the tag lands
   on the merge commit with the new version.
3. **Draft release** on GitHub: *Draft a new release*, tag `vX.Y.Z` ("create
   new tag on publish"), title and release notes, then *Save draft*.  A draft
   creates no tag and Zenodo ignores it.
4. **Push the tag:** `git tag vX.Y.Z && git push origin vX.Y.Z`.

The workflow then runs these jobs, each only if the ones before passed:

| Job | What it does |
|---|---|
| Tag and version | the tag must be `v` plus the package version |
| Latest questionnaire release | finds the questionnaire's latest published release |
| Tests | every supported Python and RDMO version, against that questionnaire release, and the documentation |
| Upload to PyPI | builds the package and uploads it (Trusted Publishing, environment `pypi`) |
| Publish the release | publishes the draft; without a draft it creates a release with generated notes |

**Dry run:** *Actions → Publish to PyPI → Run workflow* on any branch runs the
first three jobs (without the tag check): nothing is uploaded or published.

## If something fails

| What failed | What to do |
|---|---|
| Tag and version | nothing was published: delete the tag (`git push --delete origin vX.Y.Z`, `git tag -d vX.Y.Z`), fix the version with a pull request, push the tag again |
| Tests | nothing was published: fix the cause (or release the questionnaire), delete and push the tag again |
| Upload to PyPI | nothing was published; if the version is on PyPI already, it cannot be uploaded again: the next version is needed |
| Publish the release | the package is on PyPI: run only the failed job again (*Re-run failed jobs*, or `gh run rerun <run> --failed`) |

## What runs when

| Event | Tests | Documentation |
|---|---|---|
| Push to any branch | one combination (Python 3.14, RDMO 2.5.2) | built |
| Pull request to `main` or the integration branch | every combination, also on PostgreSQL and MariaDB | built |
| Merge into `main` | one combination | built and published |

See [Run and Update the Tests](tests.md) for the combinations and for
running the tests locally.
| Release (tag push) | every combination, against the questionnaire release | built |

## Requirements

- **PyPI:** a trusted publisher for the project (owner `MaRDI4NFDI`, repository
  `MaRDMO-Plugin`, workflow `pypi-publish.yml`, environment `pypi`); renaming
  the workflow needs the entry to be updated.
- **GitHub environment `pypi`:** deployments only from tags `v*`.
- **Zenodo:** the repository's webhook for releases (*Settings → Webhooks*).
- **Rulesets:** `main` and the integration branch need pull requests and the tests; tags `v*` may only be
  created, moved or deleted by maintainers.
