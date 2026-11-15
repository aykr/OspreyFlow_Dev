# The docs lane: where it stands (15 November 2026, 12:00Z, before the switch to sol)

The worktree is `~/dev/osprey-wt/docs-v052d`, and the tree is clean. Main is 9d9f048 or later. Only the orchestrator
merges.

## Open

- **`lane/docs-v060-changelog`, at 5538953 or later.** This is v0.6.0's CHANGELOG section. Add one line for each item
  as the orchestrator says it merged: **i4, i6, i10, i18, sc, us and cs** are still to come. Lines already in: rf
  (Before you install), i3, i5, i14, model keys in Admin › Models, and Bedrock London-only. i11 is process only, so it
  gets no line. Items 7 and 23 are out of v0.6.0, so nothing about them goes in. The orchestrator takes this branch
  last, at the end of Build. After each line, run `tests/test_changelog_check.py`, `test_guides_v060_fresh.py`,
  `test_guides_release_header.py` and `test_sites_design.py` (the fresh-install sentence must stay the section's
  first line).
- **§10, the guides' screenshots** (the sweep checklist's section 10, open defect A5). These are the user guide's five
  `<!-- needs a new capture -->` marks and administration guide §15's Operations image. They wait for one server
  stack, which the orchestrator leases from the candidate, seeded with the demo packs. The capture script goes in the
  repo (a small Playwright script, which needs a local slot). Use a branch of its own, separate from the changelog.
  Fix the image alt text that still uses the old sense of "view" ("The Matrix view", "every step taken in a view")
  with them (`sites-v052-facts.md`).

## Merged today, for reference

The v0.5.2 cut (CHANGELOG, headers, sites), which became v0.6.0's rename (#9). The saved-views words (V5). The model
keys (AG 2.21). Bedrock in London (AG 2.22). §6's answer's items (UG 1.71). Each has its red-first record in
`gates/`.

## How

The plants scripts are `gates/*-plants.py`, run as `python3 <script> <tree> <venv python>` on a clean tree after a
commit. They use the offline ports 59991–59994 and a fresh `PYTHONPYCACHEPREFIX` each run. Mirror spec/10 with
`python -m tests.test_admin_guide_copies --write`. Run the record checks with `make citation-check
test-file-coverage-check product-tree-link-check decision-log-publication-check` before ready-to-merge. Beat the
heartbeat at every state change.
