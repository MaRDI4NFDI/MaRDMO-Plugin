# Validation

Everything MaRDMO exports must be accepted by the MaRDI Portal; a value the
portal rejects would otherwise stop the upload halfway.  MaRDMO therefore checks
entered values in four places, which all use the same rules:

| Place | When | What happens on a problem |
|---|---|---|
| **Pre-save validation** | While the user types in the interview | The answer is not saved; the message appears below the question |
| **Preview** | First click on *Export to MaRDI Portal* | The value is shown with a red marker explaining the problem |
| **Documentation checks** | Second click, before anything is posted | The export stops with a list of errors |
| **Final export check** | After the payload is built, before anything is posted | The export stops with a list of errors |

The rules live in one place — `validators.py`, with the regular expressions in
`patterns.py` — so that the four places always agree.  The preview uses them
through template filters in `templatetags/mardmo_tags.py`.

---

## Typing rules and complete rules

RDMO saves an answer while the user is still typing.  Pre-save validation can
therefore only reject what can **never** become valid by typing on: `1`, `10.`
and `10.1000/` are all accepted for a DOI, because each can still become a
complete DOI.  These *typing rules* are kept separately from the *complete
rules* that the preview, the checks and the export apply, e.g. `DOI_RE`
(typing) and `DOI_STRICT_RE` (complete) in `patterns.py`.  Where every prefix
of a valid value is itself valid (a swMATH ID consists of digits only), one
rule serves all four places.

---

## Rules by field

| Field | While typing | Before the export |
|---|---|---|
| Short descriptions | At most 2000 characters | Additionally: present, and not identical to the name |
| Long descriptions and other answers exported as text | No line breaks | No line breaks |
| Relations (`Label (Description)`) | Format `Label (Description)` or `Label (Description) [source]` | — |
| Data properties | No mutually exclusive pair (e.g. *linear* and *nonlinear*) | Same |
| QUDT IDs | Starts with an uppercase letter, then letters, `_` or `-` | At least two characters |
| DOIs (publications, references, documentation, data set publication) | A beginning of `10.NNNN/suffix`; links (`https://doi.org/…`) are rejected | Complete `10.NNNN/suffix` (sub-prefixes such as `10.1000.10/` allowed) |
| URLs (references, documentation) | No spaces or forbidden characters, a beginning of an allowed scheme, at most 500 characters | Additionally: an allowed scheme and a domain such as `example.org` |
| swMATH IDs | Digits only; links are rejected | Same |
| Archival year | Up to four digits | Exactly four digits |
| Counts (compute nodes, CPU occurrence, processor cores, data size in items) | Digits without a leading zero | Whole number of at least 1 |
| Data size (kilobyte to terabyte) | Digits with at most one dot; a decimal comma is rejected with a hint | Positive decimal with a dot (`12`, `1.5`) |
| Formulas and formula symbols | — | Accepted by the MaRDI Portal's TeX checker (see below); no `%` comment in multi-line formulas |

Allowed URL schemes are `http` and `https`; the *source code repository URL*
additionally accepts `git`, `ssh`, `svn`, `cvs`, `bzr` and `ftp`.  Only `http`
and `https` URLs are turned into links on the export result page.

---

## Final export check

`GeneratePayload.validate_identifiers()` runs on the finished payload, before
the relation existence check and before anything is posted.  It checks every
statement and qualifier of the following kinds and lists all problems at once:

- URL values (`url` datatype)
- DOI and swMATH work ID values
- time values (`+YYYY-MM-DDThh:mm:ssZ`)
- quantity amounts (`+8`, `+1.5`)

This catches values that reached the payload without passing the other checks,
for example data written before a rule existed.

---

## Normalisation on export

Some differences are fixed on export instead of being reported, because they
never change the meaning of a value but would make the portal reject it:

| Values | Normalisation |
|---|---|
| Text, external IDs, URLs | Tabs become spaces; leading and trailing whitespace is removed |
| Formulas and formula symbols | Line breaks and tabs become spaces; leading and trailing whitespace is removed |
| Quantity amounts | Whitespace and leading zeros are removed (`08` → `+8`) |
| Archival year, reference and documentation texts | Leading and trailing whitespace is removed |

TeX reads a line break as a space, so a formula written over several lines keeps
its meaning; `\\` line breaks inside environments such as `cases` are
unchanged.  The one exception is a `%` comment, which runs to the end of its
line: joining the lines would hide the rest of the formula.  Multi-line formulas
containing a `%` comment are therefore reported (`\%`, a percent sign, is fine).

---

## Formula check

The portal validates formulas with its own TeX checker (texvc), which accepts
less than LaTeX, KaTeX or MathJax.  MaRDMO sends every formula and formula
symbol to that checker (`tex_check.py`) when the preview is rendered and when
the documentation checks run:

- Formulas are checked in parallel, with a timeout of 5 seconds, in the form in
  which they are exported (on one line).
- Verdicts are cached for a week, so unchanged formulas are not sent again.
  Failed requests are not cached.
- If the checker cannot be reached, the preview marks the formula as
  *not verified by the MaRDI Portal* and the checks do not report it; the portal
  still checks it during the upload.

**In the preview**, a rejected formula is not handed to MathJax (an unbalanced
brace would otherwise swallow the rest of the line).  It is shown as raw TeX
with a marker; the browser adds MathJax's explanation, e.g. *Missing close
brace* (`partials/_mathjax_errors.html`).  Formulas that MathJax itself cannot
render are shown the same way instead of MathJax's error box.

**Environments.**  The checker only answers *syntax error*, also for
environments it does not support, although KaTeX and MathJax render them.  When
a rejected formula contains such an environment, MaRDMO names it and lists the
supported ones.  Accepted by the MaRDI Portal (tested October 2026):

`aligned`, `alignedat`, `align`, `cases`, `array`, `matrix`, `pmatrix`,
`bmatrix`, `Bmatrix`, `vmatrix`, `Vmatrix`, `smallmatrix`

Starred variants (`align*`, `cases*`, …) are never accepted, nor are, for
example, `equation`, `gather`, `gathered`, `split`, `multline` and `eqnarray`.
The list is kept in `tex_check.SUPPORTED_ENVIRONMENTS`.

---

## Which writes are checked

Pre-save validation guards **what the user types in the interview**: it only
runs for answers saved through RDMO's project value API, which the interview
uses (the router remembers the path of the current request and checks it).
Everything else saves values without pre-save validation and is checked by the
preview, the checks and the export like all other data:

- **Project imports** — an RDMO project file may contain values written before a
  rule existed; rejecting them would make the import fail halfway.
- **MaRDMO's own writes** — values written by the handlers when an item is
  imported from the MaRDI Portal or Wikidata, and the IDs written back after an
  export.  These run inside `helpers.internal_write()`, which also covers
  handler writes during an interview request.
- **Snapshots** — creating a snapshot copies values, rolling back restores them;
  both were valid when they were saved.
- **Management commands, scripts and fixture loads**, which run outside a
  request.

In addition, `adders.py` drops imported values that cannot be stored
consistently: of a mutually exclusive pair of data properties, both are dropped
(neither side can be judged correct), and QUDT IDs that do not match the
complete format are skipped.  The documentation checks report what is missing,
so the user can complete it.

To add a rule for a new field, see
[How to Validate a New Field](../how-to/mardmo/validate-field.md).
