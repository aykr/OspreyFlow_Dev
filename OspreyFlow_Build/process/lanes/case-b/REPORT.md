# case-b · L3.7 (the grading scheme setting and its change command) · report, round 2, 9 November 2026

L3.5 was merged at a1e4091. `lane/case-b` holds L3.7 alone. Round 2 answers the orchestrator's independent review, then the lane's own review of round 2.

**Exit, met.**
- **The setting.** `grading.scheme` is a built-in scheme or a scheme file (ADR-143 Amendment 6), read beside `osprey.yaml` and rendered as `OSPREY_GRADING_SCHEME` plus `OSPREY_GRADING_GRADES`. The Conduit reads it first and refuses to start on anything unknown. It is answered at `GET /v1/grading-scheme`; a board offers its grades and refuses any other (`test_grading_setting.py`, `test_grading_boards.py`).
- **The dry run comes first, enforced (C13).**
  - The dry run writes nothing (no table either) and gives a token for the mapping on the items' state.
  - The change is refused without that token, or with one for another mapping or an earlier state (`test_the_change_is_refused_without_its_dry_runs_token_for_this_state`, `test_another_mapping_between_the_same_schemes_gives_another_token`, `test_an_edit_since_the_dry_run_is_another_state`).
- **Grades keep their original.** Only the grade and original change, in place, through `GraphPort.regrade_drawn`. Its conformance case was written first. Links are not weighed again (`test_every_item_keeps_its_original_grade_and_scheme_through_two_changes`, `test_regrade_drawn_changes_the_grade_and_original_alone`).
- **The verb.** `ospreyflow grading change` runs the script inside the deployment and refuses while the Conduit runs unless `--stop-api` is given. After a change it sets the scheme, renders and starts the Conduit; after a failure that may have written it leaves the Conduit stopped (`test_grading_verb.py`).
- **The real start-up.** A live test runs `_main` with no ontology applied, against the registry, the `AuditWriter` and a link of an L3.5 proposed type, changes the scheme and changes it back (`test_grading_change_live.py`).
- **Red record.** Every test was shown red by a plant: 61 offline and 9 live (`L3.7_RED_RECORD.md`). The plant runner now requires a green start and counts only test failures as red, with a fresh bytecode cache per run.
- **Keyboard and axe: none due.** No new screen or action.

**Gates** at `052f1c1` (tree `b1e43f1e`), on main `4310833`, with `GRADING_CI.diff` applied: `make -k ci` green throughout, the trivy scans included; `make test` 9477 passed, with this machine's 4 failures and 2 errors (the list L3.5's gate explained); test-js 2760 passed, 5 failed, none in this lane's files (`gates/052f1c1.*`).

**Live.** The whole set ran once at `71ca2fc`, alone on stack a: 384 passed, and the 9 live plants were each red. The one change since is `harness/render.py`, which no live file reads, so at the orchestrator's word the run at `052f1c1` was that delta alone, on stack c: 2 passed. Both leases are released (`gates/live-L3.7.txt`).

**The orchestrator's findings, by number.**
- **1a.** The dry run is enforced by its token.
- **1b.** The verb is built.
- **1c.** The scheme file is built: decision 11 names it.
- **1 (amendment).** ADR-143 Amendment 6 is written, and spec 01 cites it.
- **2.** One live run at the gated commit (below).
- **3.** A live test through `_main`. The command needs no ontology now that it writes the grade alone, so none is composed; the test runs `_main` with no aliases set.
- **4.** `regrade_drawn` changes the grade alone. It is guarded in its own write and its count is checked; it answers False otherwise, and the run stops.
- **5.**
  - The change is refused unless the Conduit is known to be stopped.
  - Exit 1 means only a refusal made before any write.
  - Items already drawn in the new scheme are left as they are and counted.
- **6.** Refusals name ten ids and count the rest.
- **8.** `GRADING_PARTS` is the one list of scheme names, and the Glass keeps none of its own (`test_the_built_in_schemes_names_are_listed_once`).
- **9.** `--changed-by` is recorded as typed (`changed_by_as_typed`). There is no DDL on a dry run.
- **10.** `osprey.yaml` and `data/` are not committed. The schemas commit is the branch's first, and the only one touching `packages/schemas`.

**Lane reviews.** Round 2 was reviewed by my lane-reviewer, which reported 18 findings; I fixed them all, or record them under Left. The plants then found one more defect, introduced by the rebase onto L1.6: a second `OSPREY_GRADING_SCHEME` line that named a scheme file's path. Fixed at 605cc87.

**Decisions taken** (the owner may overrule each):
1. **Promoted items are regraded too.** A later revert of a load whose link was regraded refuses that link, as for any write since. To avoid this, revert such a load before changing the scheme (Amendment 6 decision 5).
2. **A scheme file is never edited in place once items are graded in it.** A new name takes a new file (decision 4).
3. **The script on its own runs only inside the deployment.** The verb is the operator's path.

**Left.**
- The backup's configuration set (`harness/backup.py`, not this lane's file) should include `grading-scheme.yaml`.
- An install that names a scheme file: the file must sit beside `osprey.yaml`, and no test covers that install.
- `grading_change.py` imports `board_store`'s private `_ITEM_COLUMNS` and `_item`. Case could export them.
- Admin's read-only display goes to Admin.
- The six test-js failures under `ingest/`, `matrix/` and `keyboard/` (in `gates/`). They are not caused by this branch, and I did not check them on main itself.

**For the orchestrator.**
- Apply `GRADING_CI.diff`.
- Ratify these outside the lane's map:
  - `app.py`, `dataset_scope.py`, `config.py`, `harness/render.py`;
  - `cli/ospreyflow/{main,grading,answers}.py`;
  - `packages/ports/graph.py` and the ArcadeDB adapter;
  - the Glass's `boards/{BoardEditor.tsx,boardModel.ts}`, and `tests/services/api/board_fakes.py`;
  - the Build Makefile, `tools/admin_guide_options.py`, the guide 1.59 and its PDF;
  - specs 01, 03, 06 (Amendment 6) and 10;
  - the schemas commit.
- Mark Amendment 6 written, and widen its title to name the scheme file.
- Twice the shared stash was used for a moment: a bare `git stash` I ran in error, applied back by its SHA, and one `--autostash` rebase. Only my entries were touched, and none is left.

**Commits:** `git log main..lane/case-b`. Nothing of mine is still running.
