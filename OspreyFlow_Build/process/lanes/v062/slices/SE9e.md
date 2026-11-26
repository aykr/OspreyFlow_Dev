# Slice SE9e · SE9 · A recipe binds `object_ref` on a Document only to a file of the same dataset (a security part; the owner, 26 November 2026)

- **Build id:** SE9 (an item's file served under another dataset's marking)
- **Dial setting:** balanced · **Rounds limit:** 8 · **After:** nothing · **Before RL2** (the owner's word)
- **Never accepted narrower. Judged by the verifier, the server and the full gate** (the owner's word, as for SE7c).
- **From GG3b's away report, question 8 (ii)** (on `away/GG3b`): ruled "yes, a security part" (26 November 2026, 12:15
  UTC; `RULINGS.md`).

## What (the finding)

`services/ingest/recipe_rules.py` (about lines 403 to 411, "ADR-127: the text's place in the media store is the
engine's to write, never a column's") refuses binding `object_ref` or `media_kind` on a Document **only when its content
kind is `document_text`**. A Document with **no content block** may bind `object_ref` from a column. Media references are
content-addressed (`packages/adapters/media_objectstore/__init__.py`, `reference_for` about line 41:
`media/<sha256>.<ext>`), so a recipe row can name a file stored for **another dataset**; `DocumentContentService.file`
(`services/api/document_content.py` about lines 183 to 191) and the file route (`app.py` about lines 7938 to 7959) then
serve it to anyone who may read the Document, under the loader's marking, not the file's own.

## Round 1

1. **The rule:** a Document's `object_ref` names only a file **stored for the same dataset**. Refused in two places, in
   words that name the recipe entity and the property and **never** the file, its dataset or its marking (rule 3):
   - **at recipe validation** (`recipe_rules.py`): binding `object_ref` (or `media_kind`) on any Document from a column is
     refused unless the engine itself can show the file is the dataset's own (say which);
   - **at load** (`services/ingest/engine.py`, where a Document's properties are written; the engine's own writes at
     about lines 1590 and 1738 stay): a Document row whose `object_ref` is not a file this dataset stored is refused.
2. **Find what records which dataset stored a file.** If nothing does (the store is content-addressed and the same bytes
   may be held by two datasets), **stop and say so** at the top of your report, with the narrowest record you would add:
   the owner decides. Do not invent a record and do not loosen the rule.
3. **Existing recipes** (the committed and seed recipes, the PID pack): list every one that binds `object_ref` from a
   column. If any does so legitimately, stop and list it.
4. **The conformance case first (rule 1)**, then the code.

## The owner's ruling after round 1's stop (26 November 2026, 12:40 UTC)

**(a): refuse every recipe binding of `object_ref` and `media_kind` on a Document, at validation and at load; only the
engine's own writes set them. Case 3 becomes "refused" (the owner's word).** No `dataset_media` record. Both a column
binding and a fixed (`literal`) value are refused. The extract route (a caller-chosen Document whose `properties_override`
sets `object_ref`) is its own part, SE9f: not this slice's.

## The table of cases (each red first on main, the planted fault at the real call site; rule 15)

| # | Case | Expected | Red with |
| --- | --- | --- | --- |
| 1 | A recipe binds `object_ref` on a Document with no content block | refused at validation | today's rule (refuses `document_text` only) |
| 2 | A row's `object_ref` names another dataset's file | refused at load; nothing written | the validation check alone |
| 3 | A row's `object_ref` names this dataset's own file | **refused** at validation and at load (the owner, 26 November 2026: (a)) | a binding let through when the file is the dataset's own |
| 4 | The engine's own `document_text` and file writes | unchanged | the load check applied to the engine's writes |
| 5 | Refusal words | name the entity and property only | the file's dataset or marking in the words |

## Acceptance test

`OspreyFlow_Build/tests/ingest/test_document_object_ref_same_dataset.py` (new, pure; red on main).

## Checks

The acceptance test; `tests/ingest/test_recipe_rules.py`; `tests/ingest/test_pid_recipes_pass_rules.py`;
`tests/services/api/test_studio_recipes_seed_refusals.py`; `ruff check .`; `mypy packages services harness`. The load
against a store is judged by the server and the merge's live step.

## Out of scope

The PDF mapping (GG3b's Q8 (i)); the PID pack's picture references (backlog row 46); the media store's addressing.
