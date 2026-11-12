# studio lane · report · the carries step (CARRIES rows 90 and 123; ADR-140 Amendment 19), 12 November 2026

Branch `lane/studio-carries` from main; the earlier L1.7 report is in this file's history.

1. **Row 90, an import replacing an in-progress draft: met, but for one window carried (item 8).** Another
   person's draft is refused in words naming them, its version and when it was opened, and how to go on (ask them
   to make it live or discard it in Studio › Model); no confirmation overrides it. The importer's own draft is
   refused until they confirm that very version: *Replace my draft* in Studio › Releases sends the version the
   check reported, `--replace-own-draft <version>` on the command, `replace_own_draft=<version>` on the route; a
   draft discarded and opened again since is not replaced (the orchestrator's review, item 5). The plan (a dry run included) and the write each read the draft; a draft opened
   between them is refused before anything is written. The audit records whether the write replaced the
   importer's own draft. Keyboard step: `replace-own-draft-on-import-by-keyboard`.
2. **Row 123, ADR-140 Amendment 19: met, written as built** (`spec/06_DECISIONS.md`), each decision with its test.
   The Join stays fail closed; a source approver declares a source's default marking in Studio › Sources; an
   unmarked table's rows carry it before any step, at the load (manual, scheduled, watched), Test, Load Preview and
   a step's preview; audited with who, when, from and to; deployed readers flagged and drafts following; never
   lowering a bound marking, and judged again at every read against the source's marking then. The Join's
   refusal names the setting where it could help. Keyboard step: `declare-a-sources-default-marking-by-keyboard`.
3. **Decisions taken** (overrule here):
   - (a) **Another person's draft is never replaceable by an import, even confirmed.** Options: refuse; ask and
     replace on confirmation. Took refuse (strict): it is their unsaved work, and they can make it live or discard
     it themselves.
   - (b) **The importer's own draft needs a confirmation, and a dry run asks for it too.** The plan says
     `replaces_own_draft`, so the Glass shows the checkbox from the check, before anything is tried.
   - (c) **An empty cell in a marking column is not "unmarked".** Options: fill empty cells with the default; fill
     only tables with no marking column. Took the second (strict): a marked table's empty cell is a defect in its
     data, not an absent marking, and filling it would let the default stand in for what the source should say.
   - (d) **The default sets the classification alone.** Caveats and other parts are not defaulted; a pipeline
     binding them to columns an unmarked table lacks stays refused. A wider default would be a new decision.
   - (e) **The setting needs Deploy pipelines (the source approver's right) and what reading the source needs**
     (Add ingest files, Edit pipelines), since its answer is the whole source (the lane review's item 2).
   - (f) **A default is refused above the approver's clearance and above the deployment's highest marking**, as
     well as below the source's own marking. A default already above the approver is theirs neither to change nor
     to clear (the orchestrator's item 3, its strict option); otherwise clearing is allowed.
   - (k) **No change writes nothing** (no version, audit, flag or draft following); refusals are not audited, as a
     refused governance edit is not (said in Amendment 19).
   - (l) **The governance edit needs Add ingest files too**, its answer being the whole source (the orchestrator's
     item 2, rule 4).
   - (m) **The import's confirmation names a version**; a bare `true` confirms nothing.
   - (g) **A default change is a governance change**: a new version, deployed readers flagged, drafts following.
   - (h) **A default left below a raised source marking is not carried** (judged at every read), rather than
     refusing the governance edit that raised the source or clearing the default silently; the source page says so.
   - (i) **The raw rows carry the default too**, so who may read a row and a sample's markings read the same marking
     the Join and Map do. With no default, a preview and Test are refused earlier, the sample withheld (an empty
     marking cell reads as one the person may not view); with one, they run.
   - (j) **The default is looked up by the source node's own registered location**, before a run's file choice.
4. **Reviews.** My lane-reviewer at 77502ae: 13 items, two access-control blockers (a stale default carried below a
   raised source marking; the setting's answer wider than the source's read gate). Fixed, each red first: 1, 2, 4,
   5, 6 (the version taken in the store's own update; the Postgres store's live case), 7, 8, 9, 13; 10 logged as
   (j); 11 and 12 below. The orchestrator's independent review at 51f5a70: must-fixes 2 (the governance edit's
   read gate) and 3 (lowering or clearing a default above the approver) fixed red first, 1 is the gates below;
   should-fixes 4 (no change), 5 (the confirmation tied to the version), 6 (the release test's fake refusing as the
   real store does, and the open_draft window answered 409 by the store's own refusal), 7 (item 10 below), 8
   (`plants/carries_reds.py`, every plant's exact old and new text, 32 red as named in `plants/carries_reds.log`);
   notes 9 and 10 (versions and the audit's *from* taken in the store's own updates) and 12 (Amendment 19 says
   refusals are not audited). Its older gap, the governance edit judging no clearance, is a CARRIES row sent to
   the orchestrator.
5. **Carried, for the case lane (item 3 of the review):** `TargetModelStore.save_draft` writes into whichever draft
   is open, under its lock, with no owner or version check (the Model tab's own save relies on that). So a draft
   opened in the instant between the import's re-read and its save is still overwritten. The fix is the case
   lane's file: `save_draft` (and `open_draft`) given the expected owner and version, checked under the lock; the
   import then passes them. Narrow (one request's two calls), named, not fixed here.
6. **Requests at merge:** `carries_action_registry.diff` (the two keyboard ids in `INGEST_STUDIO_ACTIONS`);
   `ADR_RESERVATIONS.md` row "ADR-140 Amendment 19" to *written*. Schema changes: `ReleaseImportPlan.replaces_own_draft`;
   `SourceTable.default_marking`, `default_marking_set_by`, `default_marking_set_at`; `SourceDefaultMarkingInput`;
   generated types with each.
7. **Files outside the lane's usual ones, touched because the step needs them:** `services/api/{recipe_run,run_resources}.py`
   (the run's source store, as the list store is carried) and the lifespan's source store now the run resources'
   one (one pool, as the list store); `cli/ospreyflow/{main,conduit_client}.py` (the release verb, studio's since
   L1.7); `tests/services/api/{test_run_resources,test_recipe_run_path,test_route_rights}.py`.
8. **Red record:** `carries_RED_RECORD.md` (every new test red first), and `plants/carries_reds.py` with its raw
   `plants/carries_reds.log`: 32 plants, each red for the test it names, re-runnable.
9. **Gates** (raw records and explanations in `gates/`; the code is as at ccc7f39, and only this report and
   `gates/` follow it):
   - **make test and make -k ci at ccc7f39**, on the server (`ccc7f39.{make-test,ci}.txt`, `ccc7f39.explained.md`).
     - make test: pytest 3 failed, 12911 passed; vitest 1 failed, 3167 passed.
     - make -k ci: all but route-coverage-check.
     - This step's two failures are closed by the diffs at merge (`carries_audit_section.diff`,
       `carries_conduit_routes.diff`), shown green with them applied.
     - Two failures are not mine: `tests/harness/test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`
       and vitest `src/matrix/MatrixView.budget.test.tsx`.
     - The round at 543baaa found one defect of mine: two explanations' test paths, refused by doc-citations-check.
       ccc7f39 fixes it.
   - **The leased live run at 354d39c** on stack d (`354d39c.live*`): 35 failed, 3427 passed. None are this step's,
     and the new Postgres case passed. The code is unchanged since 354d39c.
   - **Keyboard and axe at 3f4c762** in the Mac's slot (`3f4c762.*`): 56 keyboard cases on one worker and 148 axe
     states in three themes, green. This branch's own workspace changes are byte-identical at 3f4c762 and at
     ccc7f39 (the branch's diff from its merge base under `apps/`, compared). The rebase onto b4b570d brought in
     main's Home page work (`src/home/`, `keyboard/start*`), which has its own gates.
10. **Outside the ownership map** (the orchestrator ratified, item 7): `services/api/sources.py`, the Sources page
   (`apps/workspace/src/ingest/sources/{SourcePage.tsx,api.ts,sources.test.tsx}`) and the source routes in
   `services/api/app.py` (register, the governance edit, the new default-marking route) are studio-b's (L1.6);
   its L1.9 is on main and its lane closed, so this step changed them. `services/api/target_models.py` was not
   changed (the save_draft carry).
