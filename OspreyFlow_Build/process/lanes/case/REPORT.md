# Case lane · L3.2 (the Conduit half) · report, 8 November 2026

Split by the orchestrator: A–D, F and E's Conduit half here; the rest is L3.2b (`HANDOFF.md`). Gates at the tip are in `gates/`.

**Met, each with its test (each shown red, `L3.2_RED_RECORD.md`):**
- **A:** on main (9980dee, f4754b2); the wire never names a chosen node (`test_no_listing_names_a_chosen_node`).
- **B:** five view routes, visibility in the store's query; missing items counted, never named; private to the creator; no cascade; non-members refused; reached only through its own case (`test_case_views.py`, `test_case_views_store.py`).
- **Q2:** a view's conversation and proposals are read only through the view (`test_a_private_views_*`, the `view_clause` reds).
- **C:** an unconverted case's unnamed writes never touch the original's layer, and a member with no level on the original learns nothing (`test_unconverted_case_writes.py`).
- **D:** `migrate_branches_to_views`: the dry run writes nothing; the real run, live on Postgres and ArcadeDB, leaves views and no case made from another; removed, oversized and ambiguous cases are reported; Q1, Q3 and Q4 applied.
- **E, the Conduit half:** no `…/branch*` route (`test_no_route_under_a_case_makes_a_branch`); none in services/api (`test_the_conduit_names_no_branch`).
- **F:** the gate flags every planted shape. Its tree test is strict xfail on 305 lines in 54 Glass files, for L3.2b.

**Live:** lease `case`, stack b, 15:00–15:06Z, at 346b679: 439 passed. The 3 failures were stale tests, fixed and re-run green.

**Left for L3.2b:** the Glass, which still calls the removed routes; the spec wording, with B14; the target-size carry; the gate in make ci.

**Commits:** `git log main..lane/case`, from 0679ae9; lane review round 1's fixes are 2853ff8, 0da2907, f5e4225.

**For the orchestrator:**
- Apply `ci-wiring-L3.2.patch` at the merge.
- Amend ADR-144 Am 1 for `original_layer_read_only`, and drop `Right.BRANCH_CASE` in a shared commit.
- Ratify: datasets, questions, email_extraction, document_content, review, event_scope, the alert jump in app.py, places.json and placesByRole.json, stamp_datasets, the bench script, spec 01 and 03, and other lanes' tests.

**Owner:** Q1–Q4 are answered; for review, the old "Branched" history labels kept as written. **Running:** nothing; the stack is down and the lease released.
