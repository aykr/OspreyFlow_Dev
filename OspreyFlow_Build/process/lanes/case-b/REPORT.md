# case-b · L3.5 (analyst-defined link types) · report, 9 November 2026

**Exit, met.** A proposed type's links are refused promotion until accepted and live (`test_a_proposed_types_links_are_refused_promotion_until_accepted_and_live`, `test_the_promotable_route_refuses_then_allows`). A proposed type is visible only in its own case (`test_a_proposed_type_is_visible_only_in_its_own_case`, service and route). The Model tab's block has keyboard cases (`keyboard/model-proposals.spec.ts`) and axe in dark, light and GOV.UK (16 passed). Each new test was red by a plant at its call site: 23 offline, 3 live, 11 Glass (`L3.5_RED_RECORD.md`, `plants_L3.5*.py`).
**Live,** lease case-b, stack b at bd8e9c9 (route rights, the link-type, target-model and board stores): 23 passed. Its 1 failure is main's own: `models_admin_limits_route` and `models_admin_usage_route` are missing from `test_route_rights.py` (`gates/live-L3.5-stack-b.txt`). The stack was left with no unknown status and no leftover schema.
**Gates** at `1e04d9e`, tree `2e7a57ff41b7f0a3e3ca17fbc3277bbe9553b9ee`, on main `18f46f0`, with the registry patch applied:
- `make -k ci`: everything green except the seven trivy image scans, which hit Docker Hub's 429 pull limit.
- `make test`: 8898 passed; 4 failed and 2 errored, all this machine's, each explained at the head of `gates/1e04d9e.test.txt`.
- test-js: 2738 passed; 1 failed, the Matrix timing budget, which passes run alone.
**Lane review:** one round, 10 must-fix and 9 minor findings. All are fixed except item 11, which is in ADR-143 Amendment 4's *Open* for the owner. Found at rebase: boards listed and drew under proposals' hidden storage labels (rule 3, rule 7); fixed and ratified.
**Decisions taken** (ADR-143 Amendment 4, accepted by the orchestrator): a pending type is offered in its own case only; the same name may be proposed in another case (rule 3); accepted means added to the draft model, with Direct or Probabilistic chosen; links are promotable once the model is live; `propose_types` is the right; a case reading no dataset or a composite cannot propose.
**Left:**
- L3.7, its own step.
- Case's L3.4 carries: proposed types on a case's own boards; links the change form retypes to a pending type.
- Admin: the L2.7 notifications; removing *Proposed types* and `propose_link_type`.
**Shared stacks:** `accepted` must not reach a shared stack's `link_type_proposals` before this merges, because main's Conduit refuses the status. Every live test of this step now writes into a schema it drops. `connect()` on b and c replaced the table's status check with one that allows `accepted`; that is harmless to main.
**Commits:** `git log main..lane/case-b`, 12 commits.
**For the orchestrator:**
- Apply `registry-L3.5.patch`.
- Ratify these changes outside the lane's map:
  - `app.py`: the four routes and two rights.
  - `target_models.py`: `add_extension`.
  - `boards.py`: hidden types.
  - `IngestStudio.tsx`: line 14 (the import) and line 140 (the mount).
  - `places.json` and `placesByRole.json`.
  - `every-harness.spec.ts`.
  - Tests: `test_route_rights`, `test_place_routes`, `test_investigation_levels`, `test_target_models_store` and `test_boards`.
  - Specs 01, 02, 03 and 06.
**Owner:** Amendment 4's *Open*: what the Model tab may show of a case's proposal. **Running:** nothing.
