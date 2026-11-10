# studio-b · brief L1.10b, the ceiling's carries (ADR-148 Amendment 3) · code a3e3ea3, rebased on main 77200db

1. **Packs** (`seed_internal.py`):
   - hmp and fixture-corp declare SECRET. Each writes one SECRET link by design, and the proof shows it is reached.
   - ledger, both prison-intelligence packs and enron declare OFFICIAL. Each is proved through its real builders, or by the ceiling's own row check over its files.
   - **public** declares nothing: its staged recipe and rows are judged on the host before the seed starts.
2. **Staged tables:** a run the ceiling's row check refuses removes its own step tables (`staged_run.remove_step_tables_on`), both in the pipeline's branch and in the staged engine. A removal error is logged, and the refusal is still told. Measured live against MinIO (`tests/ingest/test_deployment_ceiling_staged_live.py`: its own bucket, a lease guard, teardown). After the rebase, L1.7's join guard refuses rows of differing markings, so each owner is marked as the bookings it joins (`marked_inputs`), and the controls show the Join met them.
3. **Test judges the ceiling:** the dry run judges its rows as the load does. Verify then judges the rest of an unstaged file, after the dry run, off the loop, in the load's words. The withheld guards come first on both paths.
4. **Decisions taken:**
   - **The strict option** (rules 3 and 4; the orchestrator's finding 1): Verify judges past its sample only for an author cleared to read every row of the file. So an uncleared author's file that is above the ceiling past the sample passes Test and is refused only at Load, short of brief point 3 for that author.
   - **public** is judged by what it stages, not declared (finding 2). **Only the row check's refusals** ("load", "unreadable") remove step tables.
5. **Plants:** 27 in `l1.10b/red_plants.py`, each red for its reason at 5e8736b, none by the join guard; green 32.
6. **Reviews:** my lane-reviewer's (twice, the second after the rebase), the orchestrator's and the merger's; every finding is fixed or carried.
7. **Gates:** make test and make -k ci on the server; the live set on stack d. Files and explanation in `gates/` (named in the ready-to-merge).
8. **Ratified:** `tests/ingest/recipe_test_support.py`'s `LocalStore.delete_file` (studio's file). The studio lane was told of it, and of the `engine.dry_run_recipe` and `studio_verify` edits.
9. **Carries:**
   - Am 3's own: a staged Test judges only its sample; a backstop refusal after raw staging, or a refusal other than the ceiling's, keeps the staged rows and tables.
   - The merger's 5, 6, 9 and 11, which the merger carries.
   - Still from Am 2: the drawn item (case-b), and cloud-platform's default (P7).
10. **Left:** L1.9, after P7.
