# AD1: how to cut it (a proposal for the owner; no builder is started)

Written by the conductor on 20 November 2026 from a read-only scout of lane/platform-admin-forms (tip bfac336, 26 commits, 49
files) against main (d64ad0e), and the key review of 15 November (`Claude outputs/ospreyflow_key_review_2026-11-15/
PROMPT_ORCHESTRATOR.md`, not copied here). The scout's line numbers are its own and are not re-checked; the builder re-reads.

## What the scout found

- **Conflicts: three files, all documents.** `spec/06_DECISIONS.md` (both sides append after ADR-135 Amendment 13; the text merge is
  mechanical), `spec/10_ADMINISTRATION_GUIDE.md` (both edit the Models section; hunks not yet diffed, so judgement), and
  `OspreyFlow_Core/docs/administration-guide.md` (document-control rows: the branch's newest is 1.14, main has 1.15 to 1.19, so the
  branch's rows take the next free version).
- **The number.** The branch writes ADR-135 Amendment 14. `ADR_RESERVATIONS.md` on main already reserves "ADR-135 Amendment 14" to
  rules-b, for this same work ("add a model engine from the screen alone"), and no such heading is on main. Keeping 14 and moving
  the reservation to the slice that lands it needs no renumbering of the branch's cross-references.
- **A meaning clash, not a text one.** Main's `app.py` still has `POST /v1/admin/models/engines`. The branch removes it, adds the
  three check routes (`checks`, `check-add`, `check-cancel`) and moves the edit route to its own refusal words. The check flow
  needs `model_admin.py` symbols main lacks (`check`, `add_checked`, `model_name_refusal`, `refused_field`), so `app.py`,
  `model_admin.py`, the schemas, the generated TypeScript, `model_catalogue.py` (new) and the screen travel as one chain.
  `spec/03_CONDUIT_MIDDLEWARE.md` on main still documents the removed route.
- **Tests that fail on main today** (so red first, and the acceptance for the first slice): `test_model_engine_checks.py`,
  `test_model_key_review.py` (imports `model_catalogue`), `test_model_keys_commands.py`, `test_model_catalogue.py`, and
  `tests/cli/test_models_verb.py` (expects the CLI no longer reads `deployment.env`).
- **Still to apply at the landing** (the branch's own OWED.md): `ACTION_REGISTRY.diff` (6 ids) and `EVERY_HARNESS.diff` (4 states)
  onto `apps/workspace/keyboard/actionRegistry.ts` and `a11y/every-harness.spec.ts`; regenerate `placesByRole.json`; the
  route-coverage `CARRIES` row; move a `deployment.py` helper out of commit 6bc6eae.

## The review, at the tip (the scout's reading)

| Item | At the tip |
|---|---|
| Fix A, audit by job; no echo of a refused name | Done (the audit and the result carry the job, not the model name) |
| Fix A, a tighter model-name shape | **Not done, by the owner's ruling 23**: a generous shape (letters, digits, `. _ - : / @`, 128) with a UUID test and a per-part key test; a 16-character or lower-case hyphenated string is accepted |
| Fix B, the Edit route's words | Done for the edit route. Defaults and limits still go through `_model_admin_body`, which joins each error's location |
| Fix C, redaction | Partly: fixed words per field on the model routes; `redacted()` is still an exact match and `_model_admin_body` still uses it |
| Fix D, an unexpected error with the key in hand | **Not done in code**: `_change`, `GatewayAdmin._call` and `model_keys._run` catch only their named errors. Its test and two red plants exist; no green run |
| P2 to P7, P8 | Done (tests, with red runs recorded: 21/21, 17/17, 3/3) |
| P1 | Partly: Check covered; Edit with the odd shapes not confirmed; the two shapes ruling 23 allows are accepted by design |
| P9 | Partly: number, list and object covered; a key in a query string not confirmed |

Questions: **1** answered yes (`harness/apply.py` drops the key lines from `deployment.env` after the move; read back by
`tests/harness/test_apply_changed_settings.py`; on a failed move the key stays in the file, by design). **3** answered: the
sweep removes it (the check record is saved before the put; a check older than 15 minutes is swept), with tests. **4** answered
yes on the branch (the guide prefers the hidden prompt and warns about shell history); main lacks it. **2** (a measured run on the
real LiteLLM) is **owed**: the live step is off, nothing is run.

## The cut: three slices, in order

| # | Slice | Contents | Acceptance (red on main, green after) |
|---|---|---|---|
| 1 | **AD1a: the branch's server half onto main** | The branch brought in (merge, then the three documents resolved, Amendment 14 kept and the reservation moved to this slice, guide version 1.20): schemas and generated TypeScript, `model_catalogue.py`, `model_admin.py`, `app.py`, the CLI and `model_keys.py`, spec 03, 06 and 10, both guides (question 4's lines). Main's screen is **not** changed here | The five test files above, plus `test_apply_changed_settings.py`'s key-removal case, `schemas-check`, `route-coverage-check`, and the pure neighbours. The branch's plant records re-run red then green |
| 2 | **AD1b: the screen** | `Models.tsx`, `ModelsApi.ts`, `Models.css`, `Models.test.tsx`, the keyboard spec and harness, `placesByRole.json` regenerated, the two `.diff` files applied, the `CARRIES` row | `Models.test.tsx` (vitest) and `tsc` red on main, green after; the keyboard and axe runs go to GitHub's CI after the merge (they need a browser slot) and are listed as owed until green |
| 3 | **AD1c: the review's open items** | Fix D (three catches, none printing a value), the defaults and limits routes to fixed words, `redacted()` no longer the only guard, P1 for Edit, P9 for a query string | One new test per item, each red first on the planted shape and green after; the existing P3 plants shown green |

Why not fewer: the chain cannot be split on the check flow, and one slice for all three would be about 5,000 lines of change plus
the open items, over four rounds. Why not more: the CLI group (`models.py` without `_held`, `model_keys.py`) is the only separable
part and is small; it stays inside AD1a unless the owner wants a first, quick slice.

**Between AD1a and AD1b main's Add form calls a route that no longer exists.** The two must merge back to back, before any
release. If the owner wants no such gap, AD1a and AD1b become one slice and AD1c stays separate (two slices; the first is then
very large and at risk of the four-round limit).

## The owner's rules for keys (bind every slice)

Write-only: a key is sent once and never shown back. Replace and remove, never reveal. Audited without the key. Only a holder of
the right (`manage_models`). The server command stays as a second route. Synthetic keys only, generated at run time, in every
test and plant; no real key in any file or message.

## Questions for the owner

1. Keep ADR-135 Amendment 14 as the branch has it, and move the reservation from rules-b to AD1a? (Recommended: yes.)
2. Fix A's tighter shape: keep ruling 23's generous shape (the review's own question was a proposal against the catalogue), or tighten?
   (Recommended: keep the ruling; the review asked to be told if it was disagreed with.)
3. AD1a and AD1b as two slices merged back to back, or as one? (Recommended: two, back to back.)
4. Question 2 (the measured run on the real LiteLLM) is owed and not run. Agreed?

PL4 stays held until all three are merged and the owner gives his word.
