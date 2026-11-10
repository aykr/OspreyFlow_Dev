# admin lane · report · L2.5b: Disable's full transfer list (10 November 2026)

The branch is on main e5cc0db.
- **Offline and local gates** ran at f20513c.
- **The live run** was at 0f5c76c. f20513c..0f5c76c changes one live test file only.
- **Red record:** `L2.5b_RED_RECORD.md`, with 12 offline and 14 live plants, plus the Glass plants.

| Exit criterion | State | Proving test |
| --- | --- | --- |
| Disable completes when every item of a person's is visible: L3.8's views, boards, proposals and watches offered, moved and audited | met | `test_disable_l38_transfers.py` (live): `…four_kinds_is_offered_moved_and_audited`; keyboard `admin.spec.ts`, now with a watch |
| Refused in words while anything is withheld (409 `withheld_items`, after the visible transfers commit, which stand, naming nothing) | met | `test_admin_roles_routes.py` (the fake drives the real `refuse_if_withheld`); live `…item_above_the_administrator…`; `PeopleAndRoles.test.tsx` |
| Each recipient holds the rights its own route asks, a level on the case and the case's unit, and clears the marking (a view or board: the case's highest, Amendment 9) | met | `…l38_item_needs_the_right…`, `…another_unit`, live `…case_level_or_the_marking…`, `…unit_wide_level…`, `…unmarked_dataset…`, `…cleared_to_its_cases_highest` |
| The admin dry run is kept to the dataset's own unit | met | `test_admin_dataset_cases.py::test_a_dry_run_is_for_an_administrator_of_the_datasets_own_unit` |
| System's count of cases converted to views (ADR-144 decision 6), in words when it cannot be read | met, with the report's link recorded as a gap (Amendment 9 decision 4) | `test_admin_routes.py`, live `test_admin_converted_views.py`, `AdminPlace.test.tsx` |
| The ownership route's line is gone from `NOT_A_SECTION_S`; the Datasets sentence names Studio › 4 Runs | met | `test_admin_sections.py`; `Datasets.test.tsx` |
| Keyboard (rule 13) and axe in the dark, light and GOV.UK themes; a friction row | met | `gates/f20513c.keyboard.txt` 42/42; `gates/f20513c.axe.txt` 80/80 (`show=withheld` is new); `friction/2026-11-10-admin-disable-full-list.md` |

1. **Gates.**
   - `make -k ci` (`gates/f20513c.ci.txt`) ran with `ci-L2.5b.diff` applied. It is green except Docker's checks: 8
     image scans, opentofu and chart; Docker is off here.
   - `make test` on the server (`gates/f20513c.test.txt`):
     - pytest: 10,036 passed. It has 2 failures, main's GPU and Valkey cases, and 2 errors, Docker Hub's 429
       pull limit.
     - test-js: 2,858 passed. `MatrixView` ×2 and the `App.test.tsx` hook timed out under load; all three pass
       alone (58/58).
   - Live at 0f5c76c on stack c (`gates/0f5c76c.live.txt`): 14 plants red and 517 passed, `test_route_rights.py`
     included. The earlier re-runs found the test defects listed in the red record.
2. **Reviews.**
   - My lane-reviewer found 2 must-fixes: the red record missing, and the rollback unplanted. It also found 7 should-fixes: the cover race; the unit-wide level; the Glass's stale plan and its fail-open read; the unmarked dataset untested; spec 02 stale; no decisions logged. All are fixed.
   - The orchestrator's review is built as Amendment 9: the case's highest marking, System's words, `reach`, covers after the identity provider, and the docstrings.
   - The gates caught two problems, both now fixed:
     - the two new live files had no CI wiring;
     - System's waiting count named the migration's column, which `no-branches-check` refuses.
3. **Left:**
   - the Author-transfer route (Amendment 8 decision 4);
   - Admin's own *Delete* for a removed case's layer (for the CARRIES row that follows L2.5b);
   - a stored dry-run report System could link;
   - case's per-reader count of a view, after which Amendment 9 decision 1 may relax.
4. **Commits:** `git log e5cc0db..HEAD`. The schemas commit is first.
5. **Requests at the merge:**
   - Apply `ci-L2.5b.diff` (`ci.yml` and `Makefile`).
   - Ratify these files outside admin's map:
     - case-b's `test_person_ownership_*` (untouched);
     - `keyboard/{admin.spec.ts,admin-harness.tsx}` and `a11y/every-harness.spec.ts`;
     - specs 02, 03 and 06 (Amendment 9);
     - `test_route_rights.py` (untouched).
   - No registry ids are new.
6. **Decisions taken** (yours to overrule):
   - (a) The plan reads L3.8's own SQL inside the transfer's transaction; the Glass reads the route only for `withheld`.
   - (b) What each recipient needs, by kind (`LEVEL_NEEDED`, `NEEDS`), mirrors that kind's own route.
   - (c) A watch's and a proposal's recipient must clear the dataset's marking, with an unmarked one read at the highest.
   - (d) Covers end only after the identity provider disables the account.
   - (e) The Glass says "could not check" when the ownership read fails.
   - (f) The waiting count was dropped: the migration's own column stays out of the Conduit.
   - (g) Admin's Delete button is left for a later step (a new destructive action needs its own keyboard id).
7. **Questions:** none. **Still running:** nothing of mine. Stack c is down and released, and no agent is running.
