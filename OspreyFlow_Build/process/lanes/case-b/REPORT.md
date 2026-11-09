# case-b · L3.5 (analyst-defined link types) · report, 9 November 2026

**Exit, met.**
- A proposed type's links can't be promoted until the case's own proposal is accepted and live (`test_a_proposed_types_links_are_refused_promotion_until_accepted_and_live`, `test_another_cases_live_type_never_makes_this_cases_own_proposal_promotable`, `test_the_promotable_route_refuses_then_allows`).
- A proposal is visible only in its own case: not offered elsewhere, not withdrawable elsewhere, never named by another case's link change or board (`test_a_proposed_type_is_visible_only_in_its_own_case`, `test_a_link_change_never_names_or_uses_another_cases_proposal`, `test_a_board_neither_lists_nor_draws_under_a_proposals_storage_label`).
- The Model tab: keyboard (7 cases) and axe in dark, light and GOV.UK (20 passed).
- Every test was shown red by a plant: 29 offline, 3 live, 14 Glass (`L3.5_RED_RECORD.md`, `plants_L3.5*.py`).

**Gates** at `5d2b1d6` (tree `ca9701eb183efb0544a429bcfd85c245bcf676e7`) on main `a8ed030`, with the registry patch applied:
- `make -k ci`: green. The eight trivy scans first failed on trivy's shared cache lock, then passed on re-runs (both re-runs are in the file).
- `make test`: 9068 passed. 4 failed and 2 errored, all this machine's (explained in `gates/5d2b1d6.test.txt`).
- test-js: 2748 passed. 1 failed, the Matrix timing budget, which passes alone.

**Live:** lease case-b, stack b, at `5d2b1d6`. Route rights and the link-type, target-model and board stores: 24 passed; the 3 live plants were red; the stack was left with no unknown status and no leftover schema (`gates/live-L3.5-stack-b.txt`).

**Reviews:**
- The lane review (19 findings) and the independent review (blockers 2–3, items 4–11) are all fixed.
- Built meanwhile: the Open's strict reading, in `may_read_proposal_words` (`test_an_accepter_below_the_cases_marking_sees_no_words_and_cannot_decide`).

**Decisions taken:** recorded in ADR-143 Amendment 4.

**Left:**
- L3.7, next, on its own branch.
- To case's L3.4: the promotion writer calls `promotion_refusals` (held by `test_every_promotion_writer_asks_which_links_may_go`), and a case's proposed types on its own boards.
- To admin: L2.7's notifications; removing *Proposed types* and `propose_link_type`.

**Shared stacks:** `connect()` widened `link_type_proposals`' status check on stacks b and c to allow `accepted` (harmless to main's code). Every live test now writes into a schema it drops.

**Commits:** `git log main..lane/case-b`.

**For the orchestrator:**
- Apply `registry-L3.5.patch` (6 ids).
- Ratify these outside the lane's map:
  - `app.py`, `target_models.py`, `boards.py`, `link_changes.py`.
  - `IngestStudio.tsx`, lines 14 and 140.
  - `places.json` and `placesByRole.json`.
  - `every-harness.spec.ts`.
  - The tests `test_route_rights`, `test_place_routes`, `test_investigation_levels`, `test_target_models_store`, `test_boards`, `test_link_type_routes` and `test_link_type_service`.
  - Specs 01, 02, 03 and 06.

**Owner:** Amendment 4's *Open*: may a data engineer read a proposal's words without clearance for its case's marking? Recommended: yes, which is one line.

**Running:** nothing.
