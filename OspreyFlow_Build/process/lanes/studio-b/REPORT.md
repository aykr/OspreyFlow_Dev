# studio-b lane · report · L1.8 (the Studio's tips, who-can refusals and Domain model wording; ADR-145 Amendments 4 and 7, ADR-140 Amendments 9 and 16), 9 November 2026

1. **The row's exit: met in the code, partly on `main` by the orchestrator's ruling.**
   - **"No target model on screen": met.** The Studio says "domain model" (`IngestStudio.test.tsx`,
     `ingest-studio.spec.ts`). `tools/ui_words_check.py` finds none in the Glass's copy, and
     `tests/test_ui_words_check.py` holds the proof.
   - **Every disabled action says why and who can: built as patches.** They wait on rules-b's L2.12
     (`help/roles.ts`), which is not on `main`. The patches are `L1.8_roles_words.patch`,
     `L1.8_studio_tips.patch`, `L1.8_action_registry.diff` and `L1.8_every_harness.diff`, in that order, after
     rules-b's `admin-tips.patch` (`L1.8_PATCHES.md`). Their tests are `rightsGate.test.tsx`,
     `rightNames.test.ts` and `studio-tips.spec.ts`, each red first (`l1.8/red-studio-tips.txt`). An apply check
     on this branch with `lane/rules-b` merged ran clean: vitest 528 passed, keyboard 94, axe 30 scans.
   - Who-can names the roles that hold a right, never people: the owner's ruling, in ADR-145 Amendment 7.
2. **`ui_words_check`: met.**
   - Shown red by plants in the Glass's real string shapes (JSX text, attributes, templates, a hyphen,
     `{" "}`), and against the real Glass before the wording change (four findings,
     `l1.8/red-ui-words-real-glass.txt`).
   - Its `make ci` wiring is `L1.8_ci_makefile.diff`.
3. **Carries: all four met, each red first.**
   - **The subscribed list ids:**
     - The run path was already built (`test_subscribed_lists_seam.py`).
     - Studio's L1.5 review found the drawer's sample, Test and the run still refused a subscribed Lookup.
       Each caller now hands the engine `subscribed=subscribed_in(references)`
       (`test_subscribed_lookup_call_sites.py`).
     - Another dataset's subscription is refused at all three, and red with the filter removed.
     - A static check holds every caller, with 12 plant shapes; the check as first written missed 9 of them.
     - L1.4's stand-in is retired, held by module (`test_nothing_but_tests_seeds_a_list`).
     - ADR-140 Amendment 16 records all of this.
   - **getaddrinfo off the event loop:** a SQL read, each API page, *Test connection*, naming a connection,
     Admin › Maps' add and edit, a provider's tile and the prefetch (`test_lookups_off_the_loop.py`, each site
     red alone).
   - **The SQL byte cap:** counted in UTF-8 bytes. The server keeps the running total, so no row past the cap is
     sent or held, and the cursor stops at the cap rather than scanning the table (`test_sql_connector_live.py`;
     `l1.8/red-carry-byte-cap.txt`, red at main and at the first fix).
4. **Lane reviews: three rounds, every must-fix fixed.**
   - **The first two (byte cap, words gate, patches):** fixed in 30a670c and 95bf8b5.
   - **The third, after the rebase:** five must-fix items, all closed.
     - The live run at head is done (item 5).
     - Item 2: the three refusals added.
     - Items 3 and 4: the check refuses an empty `subscribed=`, an alias, `partial`, `run_in_executor` and a bare
       reference; it asks `run_staged_recipe` too, and scans `cli`, `scripts` and `packages`.
     - Item 5, ownership: the orchestrator ratifies at merge.
     - Gates at head are done.
   - Its minor items are also fixed: the byte cap's lower bound, the incremental-read comment, the timing figure's
     lease, the amendment, the friction row and the hash map in `L1.8_LIVE_RECORD.md`.
5. **Live, under lease studio-b on stack f, through `stack_lease.sh remote`, at 52a4b6b on main 99d92a8**
   (`gates/52a4b6b.live.txt`):
   - Files: `test_route_rights.py`, `test_phase7_exit_live.py`, `test_pipeline_run.py`,
     `test_repoint_journal_callers_live.py` and `test_sql_connector_live.py`.
   - **65 passed, 3 skipped** (spaCy is not on the server).
   - **1 failed:** the server has no git identity. It passed with a synthetic one under the same lease; the orchestrator counts that rerun, and has since set an identity on the server.
   - Two earlier runs on stack c are withdrawn: no `ospreyflow` database, then the tunnel's 0.7 s round trip and
     the owner's stop.
   - No timing figure is claimed.
6. **Gates at 28775d8 on main c467064**, offline (`gates/28775d8.*`, explained):
   - **`make -k ci`:** red only where Docker is needed (trivy, opentofu-check, chart-check). Docker Desktop is off
     by the owner's ruling.
   - **`make test`:** 24 failed, 9471 passed, 16 skipped, 30 errors.
     - 22 failures and the 30 errors need the Docker API.
     - Two come from this machine: the skip-worktree `osprey.yaml` and `graphify-out/` at the root.
     - Two come from the closed ports.
   - The lane's own tests all pass. The commits after 28775d8 change only records.
7. **Left:**
   - Applying the step 1 patches once L2.12 lands.
   - Studio's choice (L1.7) to drop the `subscribed=()` defaults, so mypy holds every caller.
   - The Deploy refusal still names the source approver role by its id, in the Conduit's words
     (ADR-145 Amendment 7).
8. **Requests at merge:**
   - Apply `L1.8_ci_makefile.diff`. The four step 1 patches wait for L2.12.
   - Ratify the files below.
   - ADR-145 Amendment 7 and ADR-140 Amendment 16 are written.
   - **Questions:** none. **Running:** nothing; no lease held.

## Decisions taken (each logged for the owner to overrule)

- **Step 1 as patches** (the orchestrator's ruling, option C) until L2.12 lands, rather than copying `roles.ts`.
- **Who-can names roles, never people** (the owner's ruling; ADR-145 Amendment 7).
- **The subscribed carry fixed in Studio's three call sites** (CARRIES row 36, as assigned). The engine's
  defaults are left to Studio (A, versus removing them in its files).
- **The byte cap's crossing row is sent without its values** (A, versus a filter on the running total, which
  makes the server scan the table).
- **The live rerun added `test_sql_connector_live.py`** (A), for the byte cap's new lower bound.

## Files outside the lane's map (ratification asked)

- Studio's: `services/api/{studio_staging,studio_verify,pipeline_run}.py` and
  `services/ingest/reference_list_import.py` (CARRIES row 36; studio knows, and its L1.5 report carries it into
  L1.7).
- Platform's: `services/api/map_admin.py`.
- Shared: `services/api/app.py` (the tile and prefetch lookups, for the getaddrinfo carry).
- `spec/06_DECISIONS.md` and `spec/ADR_RESERVATIONS.md` (the two amendments).
- The Glass files under `src/ingest/**` (the wording) are by agreement with studio.

## Commits

`git log main..lane/studio-b` (24): the words gate, the wording, the carries, step 1's patches, ADR-145
Amendment 7, three review rounds, ADR-140 Amendment 16, the live records and the gate records.
