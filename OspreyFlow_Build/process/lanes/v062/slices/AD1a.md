# Slice AD1a · AD1 · The Admin model form's server half and the key review's fixes, brought from lane/platform-admin-forms onto main

- **Build id:** AD1 (the plan's "admin model form"); cut in three by the owner's word of 20 November 2026: **AD1a** (this: the server half),
  **AD1b** (the screen), **AD1c** (the key review's open items). `slices/AD1_PROPOSAL.md` has the scout's findings and the cut.
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing
- **Status of this brief:** written by the conductor on 20 November 2026 on the owner's word ("AD1 is cut in three, as you proposed;
  start AD1a's builder when a slot frees"), from a read-only scout of the same day. **AD1a does not merge until AD1b is verified;
  the two merge back to back, with no release between** (the owner). Do not ask for the merge yourself: the conductor holds it.

## What

The branch `lane/platform-admin-forms` (tip `bfac336`, 26 commits over merge base `cc0e898`, 49 files; the repository holds it, so
`git merge` and `git show lane/platform-admin-forms:<path>` work in your worktree) holds the Admin › Models form's first slice, the
owner's rulings 18 to 28 and his key review of 15 November (fixes A to D, plants P1 to P9). Main (642 commits ahead of the base) has
none of it. This slice brings the **server half** onto main and leaves the **screen** to AD1b.

1. **Bring the branch in** (`git merge lane/platform-admin-forms` into your branch, then take the screen's files back to main's
   version; see 2). Three documents conflict and nothing else:
   - `OspreyFlow_Build/spec/06_DECISIONS.md`: both sides appended after ADR-135 Amendment 13; keep both. The branch's heading is
     `### ADR-135, Amendment 14`. **Keep it as 14.** `spec/ADR_RESERVATIONS.md` on main reserves "ADR-135 Amendment 14" to the lane
     rules-b as a draft that was never written: change that row to lane `v062 AD1a`, status `written`, with the branch's title. The
     reservation check must pass.
   - `OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md`: both edit the Models section; read both hunks and keep both meanings.
   - `OspreyFlow_Core/docs/administration-guide.md`: document-control rows: the branch's newest is 1.14, main has 1.15 to 1.19; the
     branch's rows take the next free version (check main for the highest first). Keep the branch's hidden-prompt sentences about the
     terminal variable (the review's question 4).
2. **Leave the screen to AD1b.** Take main's version of exactly these, and nothing else of the branch's, back out of the merge:
   `OspreyFlow_Core/apps/workspace/src/admin/sections/{Models.tsx,Models.css,Models.test.tsx,ModelsApi.ts}`,
   `OspreyFlow_Core/apps/workspace/keyboard/{admin-models.spec.ts,models-harness.tsx}` and
   `OspreyFlow_Core/apps/workspace/src/shell/placesByRole.json`. The generated TypeScript in `packages/schemas/generated/` and the
   Python schemas **come with this slice** (the schemas check gates them). **If main's screen no longer type-checks against the new
   generated types** (run `tsc` for the workspace: `cd OspreyFlow_Core/apps/workspace && npx tsc --noEmit`, if the worktree has the
   node tools; otherwise reason from the types), or any workspace test goes red without the new screen, **do not widen the slice and
   do not guess**: say so in your report in round 1, name the smallest type-only change that would keep main's screen compiling, and
   stop for the conductor. The two slices may then become one.
3. **Where the branch and main disagree in meaning** (not in text; the scout's findings, to re-read and confirm in code):
   `services/api/app.py` on main still has `POST /v1/admin/models/engines`; the branch removes it, adds `checks`, `check-add` and
   `check-cancel`, and moves the edit route onto its own refusal words (`_engine_refusal`), while `_model_admin_body` stays for
   defaults and limits. The check flow needs `model_admin.py` symbols main lacks (`check`, `add_checked`, `model_name_refusal`,
   `refused_field`) and the new `model_catalogue.py`. `spec/03_CONDUIT_MIDDLEWARE.md` on main documents the removed route: it comes
   with the branch's edit; confirm it. `packages/schemas/deployment.py`: both sides changed it (main has `_a_key_in_the_path`,
   identical to the branch's; the branch adds `model_looks_like_a_key` and an Amendment 14 reference in `engine_refusal`'s docstring).
   `tests/services/api/test_route_rights.py`: both sides changed it. `cli/ospreyflow/models.py`: main's `_held` reads
   `deployment.env`; the branch removes it (the owner's ruling 24). The branch's own `OWED.md` also lists "move the deployment.py
   helper out of commit 6bc6eae": read it and say in your report what it means for main.
4. **Not in this slice** (the branch's `OWED.md` and the proposal): the two `.diff` files and `placesByRole.json` regeneration (AD1b);
   Fix D, the defaults and limits routes' words, `redacted()`, P1 for Edit and P9 for a query string (AD1c); the review's question 2
   (a measured run on the real gateway: the live step is off, it is **owed**, write it in your report and in `OWED.md` if the branch's
   file travels with the merge). The branch's records under `OspreyFlow_Build/process/lanes/platform/v061-admin-forms/` come with the
   merge; leave them.

**The owner's rules for keys bind this slice and every one after it:** write-only (a key is sent once and never shown back); replace and
remove, never reveal; audited without the key; only a holder of the right (`manage_models`); the server command (`services.api.model_keys`)
stays as a second route. **Synthetic keys only**, generated at run time, in every test and plant; no real key and no fixed key-shaped
string in any file, message or commit. If any file you bring in holds a fixed key-shaped string, say so; do not carry it silently.

Binding: process/CLAUDE.md rules 3, 4, 11, 12, 15; spec/06_DECISIONS.md ADR-135 and its amendments; the 18 November ruling on the
client's name; British English. You do not edit `OspreyFlow_Core/Makefile` or `.github/workflows/ci.yml`.

## Acceptance test

Already written (on the branch): they arrive with the merge and are red on main today for the right reason (a missing module or route).
The **acceptance command** runs (all under the services/api tests folder) `test_model_engine_checks.py`, `test_model_key_review.py`,
`test_model_keys_commands.py`, `test_model_catalogue.py` and `tests/cli/test_models_verb.py` (the last exists on main and now fails
against it). Do not weaken any of them. The branch's plant records (`plants_check.py`, `plants_review.py` and their `*_run.txt`) must
be **re-run in this tree** so the red-first claim holds on main's code, not only on the branch: run each plant script as its header
says, with the environment pinned as the neighbouring tests' commands pin it (`ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9`), and put the
result next to the old one in the same folder as a new `*_run_on_main.txt`. If a plant no longer goes red, that is a finding: say which.

## Checks

Pure only. The **checks command** runs the neighbours that are green on main today and must stay so: `test_model_admin_routes.py`,
`test_model_engine_keys.py`, `test_model_engine_kinds.py`, `test_model_usage_and_limits.py`, `test_admin_models_extraction_engine.py`
(all under `tests/services/api/`), `tests/harness/test_apply_changed_settings.py` (its key-removal case is the review's question 1),
`tests/harness/test_deployment_schema.py`, then the schemas check and the route-coverage check
(`uv run --frozen python -m tools.schemas_check` and `... -m tools.route_coverage_check`, not `make`: a scratch worktree has no
`.venv`). The route-coverage check may want the `CARRIES` row the branch's `OWED.md` names: make it pass without editing the
Makefile. `test_route_rights.py` has live (Postgres) cases: run only its pure cases and say which. The line adds every mapped pure
test that scans a folder the slice changes (the specification walkers and the generated-types walkers among them). Never run
`test_apply_env`.

## Out of scope

The screen (AD1b); AD1c's items; the live measured run (owed); PL4 (the shared package move; it waits for the owner's word and for
AD1 to merge); AD5; the invite form (AD2, merged).
