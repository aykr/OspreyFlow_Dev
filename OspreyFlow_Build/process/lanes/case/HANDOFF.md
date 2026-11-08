# Case lane · handoff · L3.2 (Conduit half) → L3.2b

**Step.** L3.2 (parts A–D, F and E's Conduit half) is ready to merge per `REPORT.md`. L3.2b, by the
orchestrator's split of 8 November, takes:
- E's Glass half;
- G, "branch" out of `spec/00`–`09` (B14 in spec 08 included);
- H, the axe `target-size` carry;
- wiring `tools/no_branches_check.py` into `make ci`.

**What L3.2b starts from.**
- The Conduit holds no branch.
  - Views: `services/api/case_views.py`, five routes under `/v1/investigations/{id}/views`.
  - Asking in a view: `view_id` on `POST …/questions` and `GET …/questions`, and on the question
    candidates' accept and reject.
- The gate finds 305 lines in 54 files, all under `apps/workspace/src`. The list is in
  `REPORT.md`'s gate file. `test_no_branches_check.py::test_the_tree_names_no_branch` is strict
  xfail: remove the mark when the Glass is clean.
- The Glass still calls the removed `POST …/branch` and `…/branch-by-filter`
  (`canvas/branchNodes.ts`, `workingset/branchByFilter.ts`). It also expects the cap option
  `branch`, which is now `save_as_view`, and the questions option `branch`, now `ask_in_a_view`.
  The listing no longer sends `branched_from`. The 409 code is now `original_layer_read_only`.
- To build:
  - the Cases list with views;
  - *Save as a view* on the selection bar and in the over-cap dialog;
  - the *Views in this case* panel with share and delete;
  - *Ask the model about these* saving a private view and asking with `view_id`;
  - the GOV.UK list and form;
  - `keyboard/views.spec.ts`, with the registry ids as a diff;
  - axe in dark, light and GOV.UK.

**Open, for the orchestrator or the owner.**
- B14 (spec 08) still asks for "a link to the originating investigation", which Q1 withdrew.
- ADR-144 Amendment 1 names the old 409 code. The rename needs an amendment in 06, which is the
  orchestrator's file.
- `Right.BRANCH_CASE` is still in `packages/schemas/rights.py`; no route uses it. It is a shared
  file.
- The `from_branch` tag sits on the stored record, outside `properties`, so no port reads it yet.

**Do not redo.** The views store and routes and their access tests; part C; the migration and its
live test; the Conduit's removal and its tests.
