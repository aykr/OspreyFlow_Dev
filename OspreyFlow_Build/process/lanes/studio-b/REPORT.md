# studio-b lane · report · L1.8 (the Studio's tips, who-can refusals and Domain model wording; ADR-145 Amendments 4 and 7, ADR-140 Amendments 9 and 16), 9 November 2026

Base c467064, the branch's merge-base with `main`, throughout: the gates, the live runs and this report.

1. **The row's exit: partly met at merge, and fully met when L2.12 lands.**
   - **"No target model on screen": partial until rules-b's `admin-tips.patch` and `L1.8_roles_words.patch`
     land.** The Studio says "domain model" (`IngestStudio.test.tsx`, `ingest-studio.spec.ts`), and
     `tools/ui_words_check.py` finds none in the Glass's static copy. But Admin › Roles still renders
     "Edit target model" (`admin/sections/Roles.tsx`'s `rightWords`). That name is computed from the right's id,
     so no static scan sees it. `rightNames.test.ts` holds it, in the patch, red on purpose until
     `admin-tips.patch`.
   - **Every disabled action says why and who can: built as patches**, waiting on rules-b's L2.12
     (`help/roles.ts`).
     - The patches, in order, after rules-b's `admin-tips.patch`: `L1.8_roles_words.patch`,
       `L1.8_studio_tips.patch`, `L1.8_action_registry.diff` and `L1.8_every_harness.diff` (`L1.8_PATCHES.md`).
     - Their tests are `rightsGate.test.tsx`, `rightNames.test.ts` and `studio-tips.spec.ts`, each red first
       (`l1.8/red-studio-tips.txt`).
     - `L1.8_roles_words.patch` was rebuilt against rules-b's 18e4ca3, after rules-b removed `whyNot`. All five
       apply with plain `git apply` on this branch with 18e4ca3 merged: tsc clean, vitest 528 passed,
       `ui_words_check` clean.
   - Who-can names the roles that hold a right, never people: the owner's ruling, in ADR-145 Amendment 7, which
     now says decisions 1–4 land with those patches.
2. **`ui_words_check`: met.**
   - Shown red by plants in the Glass's string shapes, eight of them new in the review round: `&nbsp;`, `&#160;`,
     ` ` and `\xa0` between the words; and `.js`, `.jsx`, `.mjs` and `.css` files.
   - It was also red against the real Glass before the wording (`l1.8/red-ui-words-real-glass.txt`).
   - Concatenation is recorded in its docstring as unseen.
   - Its CI wiring is `L1.8_ci_makefile.diff`.
3. **Carries: all four met, each red first.**
   - **The subscribed list ids** (ADR-140 Amendment 16):
     - Every caller hands the staging engine `subscribed=subscribed_in(references)`, at the drawer's sample, at
       Test and at the run.
     - **Live through `run_staging`, against Postgres's list store and the object store**
       (`test_subscribed_lookup_live.py`). It is red with the run's `subscribed=` taken out.
     - Another dataset's subscription is refused at all three places offline, and live at the run.
     - **Rule 4:** the list's rows are withheld at the sample and at Test from a case that does not read the
       dataset, including one whose own dataset subscribes the same list (`l1.8/red-principals.txt`).
       - Test's guard goes red alone.
       - The sample has two guards (the dataset's, and a Lookup's lists'), each backing the other, so its case
         is red only with both removed. The orchestrator accepted that, as recorded.
     - A static check holds every caller (12 plant shapes; the first check missed 9 of them).
     - L1.4's stand-in is held retired, by module.
   - **getaddrinfo off the event loop** (`test_lookups_off_the_loop.py`, each site red alone). The maps' live
     files ran green at head: `test_prefetch`, `test_tile_cache` and `test_list_connector_store`.
   - **The SQL byte cap**, in UTF-8 bytes, kept by the server before a row is sent:
     - The read's own UTF-8 count is now shown to be needed: 300 truth values are under the cap by the database's
       count and over it in the file's. That case is red with the read's own count removed, live.
     - The bound for a source whose count is the smaller (booleans, or a non-UTF-8 database such as LATIN1) is
       stated in the code and in Amendment 16.
4. **Reviews: four rounds, every must-fix fixed.**
   - **This lane's three rounds:** the byte cap, the words gate, the patches, and the call-site check and its
     refusals.
   - **The orchestrator's independent review, items 1–8 and its minors:**
     - Amendment 7's status and example.
     - The exit's wording.
     - The live `run_staging` case.
     - The principal cases.
     - The byte cap's own count.
     - The records.
     - The ratification list.
     - The carries named below.
5. **Live runs, each under lease studio-b, through `stack_lease.sh remote`** (`l1.8/L1.8_LIVE_RECORD.md`):
   - **At 52a4b6b, stack f:**
     - Files: `test_route_rights.py`, `test_phase7_exit_live.py`, `test_pipeline_run.py`,
       `test_repoint_journal_callers_live.py` and `test_sql_connector_live.py`.
     - 65 passed.
     - 3 skipped: the `extraction` extra is not installed, as in CI (ADR-108); not counted as passes.
     - 1 failed: the server had no git identity. That case passed when given one, and the orchestrator counts it.
   - **The fix round at 350fbc3, stack f** (`l1.8/red-live-fix-round.txt`):
     - (a) Two plants, red for the reasons they claim.
     - (b) Green: `test_subscribed_lookup_live`, `test_sql_connector_live`, `test_prefetch`, `test_tile_cache`
       and `test_list_connector_store`, 32 passed, none skipped.
   - **Withdrawn:** two earlier runs on stack c (no `ospreyflow` database; then the tunnel's speed, and the
     owner's stop).
   - No timing figure is claimed.
6. **Gates at 350fbc3**, offline (`gates/350fbc3.*`, explained):
   - **`make -k ci`:**
     - Red on the eight image scans, `opentofu-check` and `chart-check`, which need Docker (off by the owner's
       ruling).
     - Red on `test-file-coverage-check`, which names the new live file until `L1.8_ci_makefile.diff` is
       applied. With the diff it is green.
     - The filesystem trivy scan passed.
   - **`make test`:** 25 failed, 9474 passed, 18 skipped, 30 errors.
     - 20 failures and the 30 errors need the Docker API.
     - 4 failures are this machine's: the skip-worktree `osprey.yaml`, `graphify-out/`, and two closed ports.
     - 1 failure is the coverage gate's own test, green with the diff.
   - The commits after 350fbc3 change only records, the spec and the rebuilt patch. The spec gates were taken
     again at 1339fca.
7. **Left:**
   - Applying the four step 1 patches once L2.12 lands.
   - **Two carries for studio**, which the orchestrator files at merge:
     - The Deploy refusal still names the source approver role by its id, in the Conduit's words.
     - Drop the `subscribed=()` defaults in `staging_catalogue`, `staged_run` and `reference_list_import`
       (L1.7), so mypy holds every caller.
   - rules-b's `whyNot` naming people: rules-b has removed it (the orchestrator routed it).
8. **Requests at merge:**
   - Apply `L1.8_ci_makefile.diff`: `ui_words_check`'s CI job, and `test_subscribed_lookup_live.py`'s ignore
     and live-job listing.
   - Ratify the files below.
   - ADR-145 Amendment 7 and ADR-140 Amendment 16 are written, and so marked in `ADR_RESERVATIONS.md`.
   - **Questions:** none. **Running:** nothing; no lease held.

## Decisions taken (each logged for the owner to overrule)

- **Step 1 as patches** until L2.12 lands (the orchestrator's ruling, option C), rather than copying `roles.ts`.
- **Who-can names roles, never people** (the owner's ruling; ADR-145 Amendment 7).
- **The subscribed carry fixed in Studio's call sites** (CARRIES row 36, as assigned). The engine's defaults are
  left to Studio (A, versus removing them in its files).
- **The sample's two guards kept, each backing the other** (A, versus removing the one the other shadows).
  Accepted by the orchestrator.
- **The byte cap's crossing row is sent without its values** (A, versus a filter on the running total, which
  makes the server scan the table). The read's own UTF-8 count stays as the bound for any source.
- **The live run case reads its own deployment list named `establishments`, refusing to start over another's**
  (A, versus deleting a stranger's row, rule 14).

## Files outside the lane's map (ratification asked)

- **Studio's:** `services/api/{studio_staging,studio_verify,pipeline_run}.py` and
  `services/ingest/reference_list_import.py` (CARRIES row 36). Studio knows, and its L1.5 report carries the
  defaults into L1.7.
- **Studio's, by agreement:** `apps/workspace/keyboard/ingest-studio.spec.ts` and the Glass files under
  `src/ingest/**` (the wording, on the branch). The Preview case's tip-before-press change is in
  `L1.8_studio_tips.patch`, not on the branch, and lands with it.
- **Platform's:** `services/api/map_admin.py` (Admin › Maps' lookups).
- **Shared:** `services/api/app.py` (the tile and prefetch lookups).
- **The spec:** `spec/06_DECISIONS.md` and `spec/ADR_RESERVATIONS.md` (the two amendments).
- **Shared, as diffs only:** `OspreyFlow_Build/Makefile` and `.github/workflows/ci.yml`
  (`L1.8_ci_makefile.diff`), `keyboard/actionRegistry.ts` and `a11y/every-harness.spec.ts`.

## Commits

`git log main..lane/studio-b` (32), in order:
- the words gate and the wording;
- the carries;
- step 1's patches;
- ADR-145 Amendment 7;
- this lane's review rounds;
- ADR-140 Amendment 16;
- the orchestrator's review round;
- the live and gate records.
