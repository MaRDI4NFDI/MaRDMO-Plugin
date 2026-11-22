# Question Configuration Reference

MaRDMO extracts interview answers from RDMO by reading each registered question's
configuration from `<submodule>/data/questions.json` and placing the value in the
answers by its keys and five boolean flags.  This page documents the
configuration fields and how the flags make the path.

---

## Configuration fields

Each question entry inside `questions.json` has the following fields:

| Field | Required | Description |
|---|---|---|
| `uri` | yes | RDMO attribute URI fragment (without the base URI `https://rdmo.mardi4nfdi.de/terms/`) |
| `key1` | yes | Top-level key in the answers dict — the entity class name (e.g. `"field"`, `"model"`) |
| `key2` | yes | Second-level key — the specific question name within the entity (e.g. `"ID"`, `"Name"`) |
| `key3` | no | Optional third-level key for deeply nested structures |
| `set_prefix` | no | `true` when the question belongs to a nested (collection) question set — the entity instance index is inserted into the path |
| `set_index` | no | `true` when the question belongs to a question set — the question set instance index is inserted into the path |
| `collection_index` | no | `true` when the question is a collection (multiple answers) — the answer index is appended to the path |
| `external_id` | no | `true` to extract the entity reference stored for this question as `{ID, Name, Description}` or a raw external ID |
| `option_text` | no | `true` to extract both the selected option's URI and the entered text as a `[option_uri, text]` pair — used when a question captures both a relation type (option) and a related entity name (text) |

Omitted boolean fields default to `false`.

---

## Flags and resulting paths

`rules.route()` turns a value of a question into its entry and the path of the
entry in the answers dict.

**The path** is built from these parts, in this order, each only if its flag
(or key) is set:

1. `key1`
2. `prefix_idx`, the set prefix (`set_prefix`)
3. `key2`
4. `set_index` (`set_index`)
5. `coll_index`, the collection index (`collection_index`)
6. `key3`

Without a set prefix the set index comes before `key2`: the question is on a
page of its own (`[key1, set_index, key2]`).  With one, the set index is a block
within the page (`[key1, prefix_idx, key2, set_index]`).

**The entry** stored at the path:

- `option_text`: the pair `[option_uri, text]`
- `external_id`: the item `{ID, Name, Description}`; for the ID question of a
  page (`set_index` and `external_id` only) just its `external_id`
- otherwise the value: `value.option_uri` if an option was selected, else `value.text`

Only the flag combinations the questions use are allowed (`rules.ALLOWED`); a
question with another one is an error (`tests/unit/test_rules.py` checks all
questions).
