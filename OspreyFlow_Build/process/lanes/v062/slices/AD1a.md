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

## Round 2 (the owner's ruling of 20 November 2026, after the stop on the scans): one workspace file is allowed

The scans stopped this slice on three tests: `tests/services/api/test_admin_sections.py::test_every_admin_route_is_some_section_s` and, in
`tests/services/api/test_place_routes.py`, `test_the_record_of_places_by_role_is_the_routes` and
`test_every_route_of_a_hidden_place_refuses_the_role[right:manage_models]`. The routes this slice adds (`checks`, `check-add`, `check-cancel`) are
not in the places record or the sections list, and the old add route still is. **The owner's ruling, which changes items 2 and 4 above:**

1. **This branch may change one workspace file: `OspreyFlow_Core/apps/workspace/src/shell/placesByRole.json`, and no other file under `apps/workspace`.**
   It is produced by its generator and never edited by hand: run `tests/services/api/test_place_routes.py::test_the_record_of_places_by_role_is_the_routes`
   with the environment variable `OSPREY_WRITE_PLACES_BY_ROLE=1` (the test rewrites the file from the routes), then run both place tests without the
   variable and see them pass. Say in your report that the file was generated, and by which command.
2. **The sections list** (`test_admin_sections.py` reads the admin routes against the sections): bring the new routes into whatever server-side file
   that test reads (not under `apps/workspace`). If the only way to make it green is a second workspace file, stop and say so; do not touch it.
3. **This slice still does not merge.** It stays unmerged until AD1b is verified, which is after PL4's slice E. The rule it bends (nothing else
   touches `apps/workspace` while PL4 runs) is about landing on main, and this does not land then.
4. **When main is brought into this branch before its merge** (the conductor sends it back for that): `placesByRole.json` is **regenerated again
   from main's state with the same command, never merged by hand** (if the merge conflicts on it, take main's copy first, then regenerate), and the
   three tests above are rerun and reported.
5. Everything else stands, including the screen files (take main's version of them).

## Restart (the owner's ruling of 20 November 2026, after round 4): the whole key-path table is the brief

Four rounds closed one of five fault rows. The owner restarts the rounds with **`slices/AD1a_KEY_PATHS_TABLE.md` (28 rows) as the brief. Read it first, every row.** **One design, not four patches:**

1. **Once a key is stored, the clean-up runs on every way out of the edit:** any exception (not only `ModelAdminRefused` and `OSError`), cancellation of the task, a refused credential delete, a connection dropped after the gateway wrote. Not a catch list, a structure: the stored key's
   clean-up is entered with the key (a `try`/`finally`, or a guard object whose exit does it, shielded from cancellation), so no way out skips it. A clean-up step that itself fails (the credential delete refused) is **loud, never a log line alone**: the engine is marked unavailable, the person is
   told in words, an audit record without the key says what happened, and **the undo does not rebuild old-address entries on a credential that may still hold the new key.**
2. **Start-up puts right whatever a killed process left,** including SE5's case: it compares every entry's address with the record and withdraws or refuses what disagrees, and it covers a process killed after the key was stored and before the record was saved (row 15). **Take main in first**
   (SE5 merges before you start): SE5's start-up check and its tests are on main; keep the stronger of the two behaviours where the branch's edit path and main's differ, and say in your report which you kept and why. The owner's rule on keys binds you (write-only, never shown back, audited without
   the key, synthetic keys generated at run time and no fixed key-shaped string anywhere).
3. **Acceptance: rows 3, 15, 16, 17 and 28 are each a test with a planted fault at the real call site, red first, green after:** row 3 (the key-storing call's answer is lost after the gateway stored it); row 15 (the process dies after the key is stored and before the record is saved, then a restart and a
   later key set); row 16 (the clean-up's credential delete is refused); row 17 (a cancellation, a JSON error and another transport error, each after the key is stored); row 28 (the SE5 case on this branch's edit path). The gateway stand-in models the real gateway's refusals (rule 15). Each test names, in its header, the row it holds.
4. **Everything else in the table** (rows 1, 2, 4 to 14, 18 to 27) **is re-checked by the verifier, row by row**; if a change of yours alters a row, say so in your report. Rows whose state left is "a key held for a while" (probe credentials, a cancelled check) must still be removed by the sweep or start-up; do not weaken them.
5. **Cheap checks before your final report:** ruff and eslint on every file you changed, the scan-map check for any test you add, and the three place tests of the earlier ruling (`test_admin_sections` and the two in `test_place_routes`); `placesByRole.json` regenerated again from main's state after the merge, never merged by hand.
6. **A key-handling fault is never accepted:** no standing accept, no narrower accept. If a row cannot be closed, say which and why in your report.
7. **Rows 29 to 38 of the table (what SE5 leaves open, added on the owner's word of 20 November, after SE5 merged on his accept) are part of the same design and the same acceptance:** each is an acceptance test with a planted fault at the real call site, red first. **The owner's refinement of the rule:** *a fault that can expose a key, show it back, log it or send it to an address it was not given for is never accepted; a fault that leaves an engine unavailable or the words wrong is fixed here and named in the release notes meanwhile.* The one design (the table's seven points under "rows 29 onward"): a record of intent written before a credential is deleted and cleared on success; one decision for the words and the mark across refusal, error, cancellation and any other exception; "put back" said only when it was; start-up marking every engine whose record says a key is set and has none; a reconcile clearing only what it made whole; a "not saved" answer saying when the key removal was saved.
8. **Take main in first, after SE5** (SE5 is on main when AD1a restarts): keep the stronger of the two behaviours where AD1a's edit path and SE5's differ, regenerate `placesByRole.json` from main's state as the earlier ruling says (never merged by hand), and rerun the three place tests. Say in your report which of SE5's tests you kept, which you replaced, and why.

## Rounds 7 and 8: the owner's ruling on the round-6 table (20 November, after round 6)

AD1a stopped at round 6 with five faults in behaviour (`slices/AD1a_ROUND6_TABLE.md`). **The owner gave two more rounds on that table. If a row is open after both, AD1a stops and comes to the owner with the table; it stays unmerged until AD1b is verified in any case.** Order, and every row an acceptance test with a planted fault at the real call site (red first):

1. **FIRST: row 28 on the edit path. A key that could reach an address it was not given for is never accepted.** `edit_engine` with the same address and a key stores the key **without first withdrawing disagreeing entries** (`set_key` does, at its own `_withdraw_disagreeing` call); with an entry left at the NEW address after a failed put-back, a key typed for OLD becomes the credential that entry names, the record is settled to "set" before the reconcile that would remove the entry fails, and another replica offers the engine. **The test is on `edit_engine`, and not only on `set_key`:** plant the refused `/model/delete` after a failed moved edit, then an edit that keeps the OLD address and carries a key; assert `(NEW, the OLD key)` is never sent. Fix the path, and look for any other caller that stores a key without the withdrawal.
2. **Row 40 (the regression):** a moved edit saves "key lost" **before** it withdraws the old entries; a refused withdrawal then makes the undo delete the engine's **working old key**. The old key must survive a refused withdrawal; test with a refused withdrawal (the existing rows 29/30 test stubs `_withdraw_entries` with a call that sends no write, so it covers nothing: replace it).
3. **The note of intent: ONE mechanism for every place a credential is deleted or stored and a later step can fail (the owner's ruling, which replaces the earlier "start reads credentials" design).** A note of intent is **saved before any credential is deleted or stored and cleared when the change is complete**; **start-up marks unavailable every engine with a note outstanding.** Places (the scout found these; if you find another such place it joins the same mechanism, it is not a new patch): **edit (moved and not moved), key rotation, remove key, remove engine, cancel-check, the first check (the probe credential), and any `put_credential`/`delete_credential` caller.** This closes **row 36** (an engine recorded "set" whose credential was deleted), **row 41** (cancel_check deletes the credential with no intent first) and, with the probe covered, **row 21** (a probe credential holding a typed key left by a check killed before any models file exists: start-up must also remove it when there is no models file, because it returns early today before the probe sweep).
4. **Row 36, the owner's ruling, restated in full: start-up never lists or reads the gateway's credentials, because the listing returns part of each key (the first and last two characters). A key is never shown back, to a person or to the product.** `spec/06_DECISIONS.md` (ADR-135 Amendment 14 point 9) says today "start reads the record, never a credential (`GET /credentials` answers with part of the key)" as a decision the builder took without asking: **correct the specification to the owner's ruling**, saying the ruling (the note of intent, cleared when complete, marks unavailable at start-up) **and why the listing is not used**, and say who ruled it and when (the owner, 20 November 2026; the design he gave on SE5's merge). Do not use a credential listing anywhere.
5. **"Put back" words (rows 30, 33, 34):** "put back" is said in the answer and the audit only when the undo restored the entries **and** the credential; a rotation's or remove-key's undo removes the credential and does not restore it, so it must not say so.
6. **Report a line per row of the table (1 to 41):** closed (with the test) or open (and why); keep the closed rows closed; the cheap checks before your report (ruff, the scan-map check, the three place tests). The key rules bind every row: never shown back, never logged, audited without the key, never sent to an address it was not given for; synthetic keys at run time.

## Round 8 (the last; the owner's second add-round line, 20 November, after round 7 stopped at 7/7 on tip 4b9147a)

Round 7 closed rows 28 (on `edit_engine`), 40, 36, 41 and 21 and corrected the specification to the owner's ruling (the scout and the verifier agree; no key reaches an address it was not given for, is shown back, logged or audited). **One fault in behaviour remains, and it is a fault in key handling words and audit, so it is fixed here and never accepted; if a row is open after this round AD1a stops and goes to the owner with the table.** Fix these, in this order, each with an acceptance test with a planted fault at the real call site (red first):

1. **The verifier's fault (`OspreyFlow_Core/services/api/model_admin.py` about lines 1815, 1934 to 1938, 2158 to 2162, 1706 to 1707, 1730).** A key rotation (`set_key`), or an edit that keeps its address and carries a key (`edit_engine`, `settle=not moved`), stores the new key (the old key is deleted first, then the new one posted) and **saves the record as "set" and clears the note of intent inside `_put_key` (`settle=True`)**; if `_reconcile(proposed)` or the final save then fails (a refused `/key/update`, a garbled `/key/list`, a cancellation), `_change` says "the change was not saved" and, for a cancellation or an unnamed exception, "put back as the saved settings say", although the old key is gone and the new key is the engine's credential; and no `key_rotated` audit says the key changed. **This is the same early-clear the scout called N3.** Fix it by the owner's design, not a patch: **the note of intent is cleared only when the change is complete** (the final save), for rotation and a non-moved edit as for a moved one, so a failure after the store leaves the note and the undo does what the moved edit's undo does (removes the credential, marks the key lost, and says so in the one function for the words, `_why_it_stopped`): **the answer and the audit then say what happened to the key (the old key was replaced or removed and the person must enter it again), never "the change was not saved" alone and never "put back" unless the entries AND the credential were restored.** The audit row for the failure names the key action (`key_rotated`, outcome refused or interrupted) and says the key was removed; it never carries a key. **Tests (on `set_key` and on `edit_engine` with the same address and a key, and a rotation by the first check):** plant `/key/update` refused after the store; plant `/key/list` garbled; plant a hang after the store then a cancellation; assert the record, the gateway credential, the answer's words and the audit row agree, and that "put back" is not said. Red against the tip.
2. **N1: `_expired` (about lines 2165 to 2175, called from `sweep_checks`, `check`, `add_checked`) deletes a passed check's credential with no note.** It joins the one mechanism: note saved before the delete, cleared when done; test with the delete refused (a real refusal from the stand-in).
3. **N2: the words edge for an engine whose key was already lost (`_key_taken`, about lines 1725 to 1730).** A cancelled or unnamed-exception moved edit on an engine whose key was already lost can say "put back" after `_resolve` removed a credential. Test: lost engine, moved edit with a key, cancel after the credential is stored; assert the words do not say "put back".
4. **N5: replace the rows 29/30 test that stubs `_withdraw_entries` with a call that sends no write (`tests/services/api/test_model_key_paths.py` about line 435)** with a real refused delete (the stand-in's HTTP 500 on `/model/delete`, as row 40's test does).
5. **The probe with no models file (about lines 2111 to 2134)** puts and deletes the probe credential with no note; the start-up sweep covers it, so give it the note too (the mechanism has no exception) or say in your report in one sentence why a note adds nothing (the credential is always removed at start-up and no engine state depends on it), and show the test that covers it.
6. **Not to do: no credential listing at start-up** (the owner's ruling stands). The start-up's `GET /key/list` of the gateway's virtual keys (`revoke_stale_engine_keys`) holds a SHA-256 token and no key material; **leave it** (the conductor has asked the owner; do not change it in this round).
7. **Report a line per row of the table (1 to 41, then N1 to N5):** closed (with the test) or open (and why). The cheap checks first (ruff on `OspreyFlow_Core`, the scan-map check, the three place tests). The key rules bind every row: never shown back, never logged, audited without the key, never sent to an address it was not given for; synthetic keys generated at run time.

## Round 6 (superseded by rounds 7 and 8 above): the fix round on the 38-row table (the conductor, 20 November, after the restart round)

The restart round (round 5) **did not do its work**: it reported green without merging main in, and left rows 28 to 38 without a test. The verifier and a read-only scout judged the tip `4ace506` against the table: **rows 3, 29 and 38 closed, row 30 partly, rows 15, 16, 17, 28, 31, 32, 33, 34, 35, 36 and 37 open, and a new row 39**, and the six-point design met only in part. **This is the last round the owner gave. If a row is open after it, AD1a stops and comes to the owner with the table. A key-handling fault is never accepted: rows 15, 16, 17 and 28 can send a key to an address it was not given for.**

**YOUR FIRST ACTION, before you read anything else or change anything: merge main into this branch and report the merge commit.** (`git merge main`; main now holds SE5, its tests and its code.) The restart brief (points 2 and 8) said it; round 5 did not; the verifier found `1e3092e` (SE5's merge) is not an ancestor of the tip. Resolve the conflicts (`spec/03_CONDUIT_MIDDLEWARE.md`, `spec/06_DECISIONS.md`, the administration guide with its PDF and manifest, `model_admin.py`) **keeping the stronger of the two behaviours** (SE5's undo logic, writes counter, `_withdraw_disagreeing` and start-up address comparison are on main and have tests: `OspreyFlow_Build/tests/services/api/test_model_address_change_failure.py` must pass on the merged branch), regenerate `placesByRole.json` from main's state with the generator and never by hand, and rerun the three place tests. Say which of SE5's pieces you kept, which you replaced and why.

Then, **one design** (points 1 to 6 of "rows 29 onward" in the table), with **an acceptance test per open row, a planted fault at the real call site, red first, each test naming its row in its header:**

1. **Row 16 (a key-to-wrong-address fault) and row 39 (the new `KeyMayStillBeHeld` state):** when the gateway refuses to remove the new key, the file keeps the engine at the OLD address, lost, while the credential may still hold the key typed for the NEW address. **No later reconcile (the next start, the background retry, `set_key`, `add_checked`, `remove_engine`, an edit of another engine) may rebuild old-address entries on that credential.** The exclusion today is only in the undo (`_without`); make it a property of the state: an engine whose credential may hold a key not given for its recorded address is excluded from every reconcile's wanted set (or its credential is made unusable) until the key is removed. The test: refuse the removal, then add a second engine, restart and run the retry, and assert `(OLD, new key)` never appears in what the gateway was sent.
2. **Rows 15 and 17 (key-to-wrong-address faults):** the stored key's clean-up is a structure, not a catch list (a `try`/`finally` or a guard object whose exit does it, shielded from cancellation): a refusal, an `OSError`, a cancellation, a JSON error from a gateway answer, any other exception, **and the process dying** (start-up: a restart after the kill between the key store and the save must not remake old-address entries on a credential holding the new key: it removes that credential or excludes the engine, as in point 1). Tests: a kill between the key store and the save then a restart; a cancellation after the store; a JSON error after the store.
3. **Row 28 (the SE5 case on this edit path):** an entry at the NEW address that survives a refused put-back; a later `set_key` stores the key and the surviving entry sends it to the NEW address. After main is in, SE5's address comparison covers it: show the test.
4. **Rows 30 to 35 (write intent before a credential is deleted, one decision for the words and the mark):** the moved edit already writes the mark before the delete; **rotation, `remove_key` and `remove_engine` do not**: each marks the engine (or writes an intent) before the delete and clears it only when the record and credential agree. One decision for refusal, `OSError`, cancellation and any other exception: the answer and the audit say "put back" only when the undo restored the entries **and** the credential; a cancel or unnamed exception gets words and an audit too.
5. **Rows 36 and 37 (start-up):** start reads credentials as well as entries: it marks every engine whose record says a key is set and has none, and every engine whose unpriced rebuild did not finish (today only a log line, with the engine offered).
6. **Row 31:** a "not saved" answer says when the key removal was saved, with a `key_removed` audit.
7. **The row-16 test already in the file passes while the fault stands** (it tries only a model-only edit, which is refused anyway): replace or extend it. Update the file's header to say rows, not rounds.
8. **Report a line per row of the table** (1 to 39): closed (with the test) or open (and why). Do not leave a row unreported. Keep closed rows closed. The cheap checks before your report: ruff on every changed file, the scan-map check, the three place tests.
