# How to Validate a New Field

A value the MaRDI Portal rejects stops the export halfway, so every field with
a fixed format is checked in four places: while typing, in the preview, in the
documentation checks, and in the final check before anything is posted (see
[Validation](../../concepts/validation.md)).  This page shows how to add such a
rule, using the swMATH work ID of a software reference as the example: it must
be a number such as `7554`, not a link.

All four places call **one shared rule**, so that they always agree.  Write the
rule once and only connect it in each place.

---

## Step 1 — Decide on the rule

Answer two questions before writing code:

- **What does the portal accept?**  Check the property on the MaRDI Portal
  (format constraints, examples).  For swMATH work IDs: digits only.
- **Is every beginning of a valid value itself valid?**  RDMO saves while the
  user types, so pre-save validation must accept unfinished input.
    - If yes (swMATH: `7`, `75`, `755` are all valid), one rule serves all four
      places.
    - If no (a DOI `10.` is unfinished, not wrong), write a *typing rule* that
      only rejects what can never become valid, and a *complete rule* for the
      other three places.  Compare `DOI_RE` and `DOI_STRICT_RE` in
      `patterns.py`.

---

## Step 2 — Pattern and shared rule

**File:** `patterns.py` — add the regular expression with a docstring that
names its format and where it is used:

```python
SWMATH_ID_RE = re.compile(r'^[0-9]+$')
'''swMATH work ID: digits only (format of Wikidata property P6830).

Every prefix of a valid ID is valid, so the same pattern serves the pre-save
validator, the preview, the documentation checker, and the export.
'''
```

**File:** `validators.py` — add a `*_problem()` function that returns a message
for the user, or `None` if the value is fine.  Ignore leading and trailing
whitespace (it is removed on export) and treat an empty value as "nothing to
check" — whether a value is required is decided elsewhere:

```python
def swmath_problem(swmath_id):
    '''Return what is wrong with a swMATH work ID, or ``None`` if it is valid.'''
    swmath_id = (swmath_id or '').strip()
    if not swmath_id:
        return None
    if _looks_like_link(swmath_id) or '/' in swmath_id:
        return 'Enter only the swMATH number (e.g. 7554), not the link'
    if not SWMATH_ID_RE.match(swmath_id):
        return 'swMATH ID must be a number (e.g. 7554)'
    return None
```

Messages should say what to enter, ideally with an example, since users see them
directly.

---

## Step 3 — Pre-save validation

**File:** `validators.py` — add a validator that receives the RDMO `Value`
about to be saved and raises `rest_framework.exceptions.ValidationError` with
the message under `text`.  RDMO shows that message below the question.  If the
question offers several options (DOI, URL, swMATH ID, …), react only to your
own option:

```python
def validate_swmath(instance):
    '''Reject a swMATH work ID that is not a number.'''
    if not instance.option or not instance.text:
        return
    if instance.option.uri != get_options().get('SWMATH'):
        return
    problem = swmath_problem(instance.text)
    if problem:
        raise ValidationError({'text': [problem]})
```

**File:** `builders.py` — register the validator for each question and catalog
in `build_presave_validator_map()`:

```python
f'{base}{questions_algorithm["Software"]["Reference"]["uri"]}':
    validate_reference,
```

Each attribute URI can have only one validator per catalog.  If a question
needs several (references accept DOIs, URLs and swMATH IDs), combine them in
one function that calls the individual validators, as `validate_reference` does.
Remember the model catalogs: the full and the basic catalog are registered
separately.

You do not need to handle imported data: values written by MaRDMO's handlers
skip pre-save validation and are checked by the steps below.

---

## Step 4 — Preview marker

**File:** `templatetags/mardmo_tags.py` — expose the rule as a template filter
that returns the message, or `''`:

```python
@register.filter
def swmath_problem(swmath_id):
    '''Return what is wrong with a swMATH work ID (same rule everywhere), or ``''``.'''
    return _swmath_problem(swmath_id) or ''
```

**File:** the preview template (here `templates/MaRDMO/partials/_reference_block.html`)
— show the value followed by the marker, so the user sees what is wrong with
which value:

```django
{{ reference.1 }}{% with problem=reference.1|swmath_problem %}{% if problem %} <strong class="mardmo-error">{{ problem|upper }}</strong>{% endif %}{% endwith %}
```

Add `{% load mardmo_tags %}` at the top of the template if it is not there yet.

---

## Step 5 — Documentation check

**File:** `checks/base.py`, `checks/model.py`, `checks/algorithm.py` or
`checks/workflow.py` — call the same rule and add an error naming the section,
the page and the problem.  For references this happens in
`ChecksBase._check_references`:

```python
elif option_key == 'SWMATH':
    problem = swmath_problem(entry[1])
...
if problem:
    self.err.append(self._error(section, page_name, f'Invalid {label}: {problem}'))
```

---

## Step 6 — Export

**Normalise** values whose problems never change their meaning, instead of
reporting them.  For references, `PublicationExport._add_references` removes
leading and trailing whitespace before the statement is added.

**Final check.**  **File:** `payload.py`, `GeneratePayload.validate_identifiers()`
— add the property to the values checked before anything is posted:

```python
swmath_pid = properties.get('swMath work ID')
...
elif prop_id == swmath_pid:
    problem = swmath_problem(text)
...
def relevant(prop_id, data_type):
    return data_type in ('url', 'URL', 'time', 'quantity') or prop_id in (doi_pid, swmath_pid)
```

This catches values that reached the payload without passing the other checks,
for example answers saved before the rule existed.

---

## Step 7 — Test

Check each place with a valid value, an unfinished value, and a wrong one:

1. **Pre-save:** in the interview, enter `7554` (saved), `https://swmath.org/software/7554`
   and `75a4` (rejected with a message below the question).
2. **Preview, checks, export:** write a wrong value past the validator — for
   example in a Django shell inside `helpers.internal_write()`, or by
   temporarily removing the registration — and confirm that the preview shows
   the marker, the checks list the error, and the export is blocked with the
   value named.
3. **Imported data:** select an existing item from the MaRDI Portal that carries
   the field and confirm that the import is not blocked.
4. **Docs:** add the rule to the table in [Validation](../../concepts/validation.md).
