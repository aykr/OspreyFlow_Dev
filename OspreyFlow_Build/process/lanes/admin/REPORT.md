# admin lane · report · L2.5c: Admin's Delete for a removed case's layer, and refusals that name roles (10 November 2026)

Gated head **3bd210d**, on main 7bdd33b; the commit after it adds this report and the records only. Red record:
`L2.5c_RED_RECORD.md` (10 plants, each red at its call site).

| Exit criterion | State | Proving test |
| --- | --- | --- |
| An administrator deletes a removed case's layer by keyboard after its dry run | met | keyboard `admin.spec.ts`, "…deleted by keyboard after its dry run" (red first); `Datasets.test.tsx` |
| The dry run gives the counts, never "would delete N" (ADR-143 Am 5 decision 11); a refused Delete drops it; the cases are read again; focus is moved; "It cannot be undone." is said | met | `test_admin_dataset_cases.py`; `Datasets.test.tsx` (the real 404 body, a second `GET …/cases`) |
| No Admin refusal names a person: `not_an_author` carries the right, and the Glass names the roles | met | `test_a_dry_run_merge_is_an_authors_and_names_no_one`; `Datasets.test.tsx`, "…by the roles that may act" |
| The census line removed; axe in three themes; a friction row | met | `test_admin_sections.py`; `gates/3bd210d.axe.txt` 84/84 (`show=delete`); `friction/2026-11-10-admin-delete-and-role-refusals.md` |

1. **Gates at 3bd210d**, each with `registry-L2.5c.diff` applied:
   - `make -k ci`: green except Docker's checks (8 image scans, opentofu, chart).
   - `make test` on the server:
     - pytest: 10,097 passed. The 2 failures are main's GPU and Valkey cases; the 2 errors are Docker Hub's 429.
     - test-js: 2,902 passed, with `MatrixView.budget` failing under load.
   - keyboard: 43/43.
   - axe: 84/84.
   - Live on stack c under the admin lease: 376 passed, including `test_route_rights.py`.
2. **Review:** my lane-reviewer found 4 must-fixes, all fixed:
   - the dry run's "would delete N";
   - no red record;
   - the re-read untested;
   - the refusal path's mock in the wrong shape.

   Its should-fixes were fixed too: the refused Delete's state, the role words, the case's name, focus and undo,
   `no_layer`, and spec 02. Left by name: `ROUTES` in `test_admin_dataset_cases.py` still omits the Delete route.
   Its access tests are in `test_promotions.py` and `test_route_rights.py`.
3. **Commits:** `git log 7bdd33b..HEAD`.
4. **Requests at the merge:**
   - Apply `registry-L2.5c.diff`. It adds 1 id to `ADMIN_ACTIONS`.
   - Ratify these files outside admin's map:
     - `a11y/every-harness.spec.ts`;
     - `keyboard/{admin.spec.ts,admin-harness.tsx}`;
     - `LayerActionRefused`'s optional `right`, shared with case's Studio routes;
     - specs 02 and 03.
   - **Docs carry:** `spec/10_ADMINISTRATION_GUIDE.md:1209-1211` says Admin offers only the dry runs.
5. **Decisions taken** (yours to overrule):
   - (a) Admin's Delete takes one press after its dry run, the dry run being the confirmation, with "It cannot be
     undone." said beside it.
   - (b) The refusal names the level (Author) and the right; the Glass says which roles hold the right.
   - (c) Refusals naming the person the administrator chose (a recipient, a lead) are left as they are. They name the
     administrator's own choice, not who holds a right.
6. **Questions:** none. **Still running:** nothing. Stack c is down and its lease released.
