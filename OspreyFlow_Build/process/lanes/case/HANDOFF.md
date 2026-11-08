# Case lane · handoff · L3.2 (the Conduit half) → L3.2b

**Step.** L3.2 is ready to merge per `REPORT.md`: parts A–D, F and E's Conduit half. L3.2b, by the
orchestrator's split of 8 November, takes E's Glass half, G ("branch" out of `spec/00`–`09`, with B14
in spec 08), H (the axe `target-size` carry), and `tools/no_branches_check.py` in `make ci`.

**First exit: L3.2b merges before the run's single push.** Until it does, `main`'s Glass breaks
where it touches a branch:
- it calls the removed `POST …/branch` and `…/branch-by-filter` (`canvas/branchNodes.ts`,
  `workingset/branchByFilter.ts`);
- it expects the cap option `branch`, now `save_as_view`, and the questions option `branch`, now
  `ask_in_a_view`.

**What L3.2b starts from.**
- Views are `services/api/case_views.py` and five routes. Asking in a view is `view_id` on
  `questions` (POST, GET) and on question candidates' accept and reject. The listing no longer
  sends `branched_from`. The 409 code is `original_layer_read_only`.
- The gate finds 304 lines, all under `apps/workspace/src`. Its tree test is strict xfail: drop the
  mark when the Glass is clean.
- To build: the Cases list with views; *Save as a view* on the selection bar and in the over-cap
  dialog; the *Views in this case* panel (share, delete); *Ask the model about these* saving a
  private view and asking with `view_id`; the GOV.UK list and form; `keyboard/views.spec.ts` with
  the registry ids as a diff; axe in dark, light and GOV.UK.
- Carried: collapsing resolved entities at a view's own threshold
  (`test_a_view_opens_collapsed_at_its_threshold`, spec 03 §3.1b).

**Left for admin (a line for L2.5b).** ADR-144 decision 6's count on Admin › System: cases converted
to views, in how many cases, with the dry run's report. The migration prints it; the screen is
admin's.

**Open.** B14 still asks for an origin link that Q1 withdrew. ADR-144 Amendment 1 names the old 409
code. The `from_branch` tag sits outside `properties`, so no port reads it yet.

**Do not redo.** Views and their access tests; part C; the migration and its live tests; the
Conduit's removal and its tests; `Right.BRANCH_CASE`'s removal.
