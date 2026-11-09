# admin lane · report · L2.7: *Needs you*, Admin's tips and Home's *What you can do* (9 November 2026)

This is round 2, after the orchestrator's independent review sent c8c9e44 back, and round 3, after my lane-reviewer's
pass over round 2.
- The branch is rebased onto main e76cef9 (round 1 was on 8e74fc8, not the f382e12 its records said). The head is in
  `git log`.
- Every case is red by a plant at its call site (`L2.7_RED_RECORD.md`, rounds 1 to 3).
- Rules was told about `src/home/` by the orchestrator at about 19:15, and has no conflict.

| Exit criterion | State | Proving test |
| --- | --- | --- |
| 1. *Needs you*: an overdue promotion served only to a current recipient, while it waits, cleared to the dataset's and the items' marking; proposals counted only in the reader's reach and only where they may read them, nothing said of the rest | met | `test_needs_you.py` (10); `test_waiting_promotions_contract.py` (with `items_marking`, C5 and C6); `test_promotion_ageing.py`; `needsYou/*.test.tsx`; keyboard `needs-you.spec.ts` |
| 2. Admin's *Proposed types* removed | met | `AdminPlace.test.tsx`, `AdminSections.test.tsx`; `test_link_type_routes.py`'s list case |
| 3. Connections' SQL, API and JSON fields; no secret returned | met | `test_admin_connection_fields.py`; `Connections.test.tsx`; keyboard (API, SQL, JSON, Test) |
| 4. The grading scheme, read-only | met | `GradingScheme.test.tsx`; `test_admin_sections.py`'s `REFERENCE_READS` pin |
| 5. Tips; refusals naming roles, never people; Home's section | met as far as sources exist (item 2) | `adminWords.test.tsx` (every section and Home, W1–W4); `refusals.test.tsx`; `home/answersFor.test.tsx` |
| Keyboard (rule 13) | met | `gates/cb1b1fa.keyboard.txt`: 703 passed. Its 2 failures are main's `boards.spec.ts` |
| axe in dark, light and GOV.UK | met | `gates/cb1b1fa.axe.txt`: 760/760 |

1. **Gates.**
   - `make -k ci` at b85a1b6 (`gates/b85a1b6.ci.txt`): green except Docker's checks (the 8 image scans, opentofu and chart).
   - `make test` on the server at b85a1b6 (`gates/b85a1b6.test.txt`), and again at 1179875 after the re-review's test-only fix (`gates/1179875.test.txt`): pytest 9,674 passed and 2 failed (main's GPU and Valkey cases); test-js 2,869 of 2,870, with `MatrixView.budget` failing under load.
   - Live on stack f at b85a1b6 under the admin lease (`gates/b85a1b6.live.txt`): 183 passed, including `test_route_rights.py`. 16 leftover `test_link_type_store` rows removed. Counted before and after, the set left no row.
   - Keyboard and axe ran at cb1b1fa. After that the Glass changed only in test files and a harness comment.
2. **Left, with why:**
   - Home's *through a team*, *Lead of*, *Covering*, *Owner of watches* and the waiting counts on *Author of* lines. No
     read gives them; spec 02 records this (rule 11).
   - An overdue promotion opens nothing for an Author without `operate_schedules` until L3.4's review screen exists.
   - The top bar re-reads on its minute.
   - Done on top of case's L3.4, by agreement: `WaitingFromStore._as_pending` passes `items_marking`, the highest current marking of its items. The contract's case is now `p-item-high`, with a derivation test (round 5 of the red record).
3. **Commits:** `git log e76cef9..HEAD`. The two schemas commits (`NeedsYou`, then the flag's removal) go before their code.
4. **Requests at the merge:**
   - Apply `registry-L2.7.diff`: 16 ids in all, made at this tree (the `index` line is its blob, 86c45ad).
     - `NEEDS_YOU_ACTIONS`: 6.
     - `ADMIN_ACTIONS`: 8 of this step's, plus rules-b's 2 from `admin-tips.patch`. Check main for duplicates of those two.
   - Ratify these files outside admin's map:
     - rules': `home/{HomePage.tsx,answersFor.ts,answersFor.test.tsx,AnswersForSection.tsx}`, `shell/startScreen.tsx`,
       `rights/visibility.ts`;
     - studio's: `ingest/IngestStudio.tsx`, `keyboard/ingest-studio-harness.tsx`;
     - case-b's: `linktypes/ModelProposals.tsx`, `services/api/{link_type_store,link_types}.py` (the narrowing and
       `open_proposal_count`), `test_link_type_{routes,service,store}.py`, `test_analyst_link_types.py`;
     - case's (L3.4's seam): `services/api/promotion_store.py` (`_as_pending`, the probe), `test_waiting_promotions_contract.py`, `test_promotion_sweep_live.py`;
     - no listed owner: `App.tsx`, `a11y/every-harness.spec.ts`, `test_route_rights.py`, `test_reports_viewer_journey.py`,
       `keyboard/{admin.spec.ts,admin-harness.tsx,needs-you.spec.ts,needs-you-harness.*,answers-harness.*}`, spec 02 and 03;
     - from the two patches: `help/roles.ts`, `help/rightNames.test.ts`.
   - Case-b: `linktypes/ProposedTypes.tsx` and its keyboard spec and harness have no screen now.
5. **Decisions taken** (yours to overrule):
   - (a) *Needs you* is one route naming no right, each half gated by what it lists.
   - (b) Withdrawn in round 2 by your ruling: nothing is said of a dataset above the reader's clearance.
   - (c) The routes for proposals naming no dataset are kept with no screen, their list narrowed in the query.
   - (d) A secret's field that isn't name-shaped is never sent; the Conduit redacts what it refuses.
   - (e) Grading scheme exempts its reference read, pinned to that one route.
   - (f) *Why* names the reader's own roles.
   - (g) Openings across a reload are held in the session.
   - (h) `items_marking` is required with no default, read from the seam at each read, and not copied into the alert store.
   - On case's L3.4 (round 5): `make test` on the server at fbd0722 (`gates/fbd0722.test.txt`): pytest 9,839 passed and 2 failed (main's GPU and Valkey cases), plus 2 errors from Docker Hub's pull limit on the server; test-js 2,884/2,885 (`MatrixView.budget`). Live at dbf925c on stack f (`gates/dbf925c.live.txt`): 25 passed.
6. **Questions:** none. **Still running:** nothing. Stack f is down and its lease released; no agent of mine is running.
