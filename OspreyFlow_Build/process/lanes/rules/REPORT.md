# rules lane · report · L2.9, four places: Rules and Monitoring, /alerts/<id>, the way back (8 November 2026; after three review rounds)

1. **Rulings:**
   - **The owner's ruling on Q1 (a), relayed by the orchestrator, 8 November:** the *Rule author* gains `read_alert_queue`, since whoever triages must read the queue. ADR-112 Amendment 5 decision 2's list is amended in ADR-146 Amendment 2 point 5. The change is in `rights.py`'s `RULE_AUTHOR`, in the branch's schemas commit. ADR-112 Amendment 5's test "Rule author opens Rules and Monitoring" is a passing test now, no longer an xfail; it is red on the role without the right, and so is `test_rights.py`'s Rule author case. The role is offered Rules and Monitoring and the Glass (whose Home reads the same queue), never the Studio; the orchestrator agreed.
   - **`needs` kept, the orchestrator agreeing:** it was asked to be dropped as interim. It is not interim: it is ADR-145 Amendment 1's entry-read rule, and the Rule author now passes it. Dropping it would offer the place to a custom role holding `triage_alerts` alone, whose first screen refuses it, and `places.test.tsx` would go red against `placesByRole.json`.
   - Q2 (a), the orchestrator's settlement: the Data Engineer's and the Administrator's losses are as in ADR-146 Amendment 2 point 2.
   - Decisions taken:
     - Held rows are shared with the Studio's Runs.
     - Connection strength stays in the Glass, under More.
     - `/rules` is the place's address.
     - The view is named "From alert: ‹title›".
2. **The fourth place: met.**
   - R&M is in the switcher and the GOV.UK header, with the open-alert count. It is offered for `triage_alerts` or `author_rules`, together with the queue's read (`places.json` `needs`).
   - Every route of the place asks for the place's gate after its own right. The four exceptions are shared outside it (two reads, two writes: the queue list, and held rows' list, reject and release).
   - Its tabs are Alerts, What raises alerts, Held rows and Changes.
   - Tests: `test_place_routes.py`, red with the gate taken off `deploy_typology_rule`, with the gate open to all, and with an unplaced rule route. Also `places.test.tsx`, `keyboard/shell.spec.ts` and `rules-place.spec.ts`.
3. **Monitoring leaves the Glass: met.** The banner is Case · Boards, and Connection strength moves under More. The count is unchanged at 24 (`App.chrome.test.tsx`).
4. **`/alerts/<id>`: met.**
   - `GET /v1/alerts/{id}` scopes the reader to the alert's case before reading. Seven cases a reader may not see answer exactly as a missing alert (`test_alert_address.py`; the reds were re-taken in RED_RECORD §6).
   - A History-API router; Home's rows open the alert; an address is ignored for whoever the place is not offered to.
   - B14 is at the alert's address (spec 08; `test_phase8_exit_over_the_wire.py`).
5. **Open the evidence: met.**
   - It saves a private view of the case and opens L3.2b's lens with *← Back to the alert*, which returns to the same alert, still open.
   - A failure is said on the alert alone. Round 3 found a stale "could not be opened" left over the Glass; it is fixed, with the red first (RED_RECORD §8).
   - Tests: `App.test.tsx` and `rules-place.spec.ts`, each red.
6. **Keyboard and axe: met.** Every new action has its case, and its registry id is in `registry-L2.9.patch`. Axe passes in dark, light and GOV.UK.
7. **Gates at 570fdf1** (tree 93a8e1e4fc1a87ed47dc4b9b2c5ea90f008dcf04), rebased on main at 9db6817, offline, with closed ports and `OSPREY_LANE` unset (`gates/570fdf1.*.txt`):
   - **`make -k ci`:** every target green except the seven `trivy-image-*` builds, refused by Docker Hub (429 Too Many Requests on `python:3.12-slim` and `nginx:1.30-alpine`). This is environmental, and the same at 23c8938.
   - **`make test`:** 8,664 passed, 4 failed and 2 errors, all this machine's own and none in rules code. The same set failed at 6c5db53.
     - `osprey.yaml` names `osm-local-great-britain`.
     - The closed-port `VALKEY_PORT` is exported.
     - `graphify-out/` sits at the root.
     - The phone fixture needs an object store.
     - The two errors are the workspace-proxy image, refused by the same 429.
   - **`test-js`:** the workspace's vitest ran 2,707 of 2,708 green. The miss was the MatrixView first-frame budget, a timing case run under load; alone it is green (`gates/570fdf1.keyboard.txt`).
   - **`glass-a11y`:** 545 passed.
   - **`glass-keyboard`:** 607 passed and 1 skipped (the screenshots case), run with `registry-L2.9.patch` applied uncommitted. Without the patch the suite cannot load (`RULES_PLACE_ACTIONS`).
8. **Live (rules lease, stack a, at 570fdf1, 21:27–21:33Z):** 18 suites, covering the place, the address, and the alert, rule, monitoring, screening, held-row and watch routes. 1,493 passed and 2 failed, both failing on main (`gates/570fdf1.live.txt`):
   - P2's two model routes are missing from `ROUTE_RIGHTS`.
   - The shared database's leftover rules break the rule list (L2.8d's record).
   - Before the rebase onto P2, at eff80cf: 21 failures and 2 errors, all explained and fixed here. 13 of them fail on main.
9. **Reviews:** three rounds by my own lane-reviewer.
   - Round 1: 8 must-fix and 4 minor.
   - Round 2: 4 must-fix and 7 minor.
   - Round 3: no code must-fix. Its must-fix items were this report and the gates. Minor 3 (the stale problem) is fixed; the "two shared reads" wording and a keyboard case's title are corrected; the rest are in item 13.
   - **The orchestrator's independent review is still owed** (the brief: the step touches access).
10. **Questions for the owner:** none open.
11. **Ratify (outside rules' map):**
    - Case lane: `views/ViewLensBanner.tsx` and `views.css`, and the jump tests removed in `test_case_writes`, `test_case_domains` and `test_drawn_datasets`.
    - Shell and harness:
      - `App.tsx`/`App.test.tsx`, `rights/visibility.ts`, `assessment/api.ts`.
      - The keyboard specs and harnesses, and `a11y/every-harness.spec.ts`.
      - `live/capture-kit.ts`/`pid-capture.spec.ts`; the captures will need retaking.
    - Conduit and tests: `app.py`, `history_labels.py`, `packages/schemas` (`AlertAtAddress`, and `rights.py`'s `RULE_AUTHOR`, in their own commit), `tests/schemas/test_rights.py`, the scenario tests, and the other jump-test lists.
    - Spec: 01, 02, 03, 08 and the 06 append.
12. **Requests:**
    - Commit `registry-L2.9.patch` at the merge.
    - Mark ADR-146 Amendment 2 `written`.
    - Platform: add P2's `models_admin_limits_route` and `models_admin_usage_route` to `test_route_rights.py`'s `ROUTE_RIGHTS` (passed on by the orchestrator).
    - Docs lane: the user guide's "Jump into investigation", and the PID captures.
    - Case lane: the dead `refuse_copying_a_drawn_dataset`/`read_the_same_dataset`.
13. **Left, minor:**
    - The address test has no team-shared positive case and no read-only-layer case.
    - Some stale jump prose remains in schema docstrings.
    - The harnesses mirror App's wiring; App.test covers the real wiring.
    - A superseded `openLens` leaves the address with no lens open (round 3, minor 4).
    - `PostgresAlertStore.case_of` is reached only by B14's live run (round 3, minor 5).
    - B14's over-the-wire step checks that the node list is not empty, not that it holds the referents (round 3, minor 6).
14. **Commits:** main..HEAD, 20 with this one. The `wip(rules)` rewrite was not needed: the paused session left only proper commits, plus an uncommitted `HANDOFF.md` and two partial gate files, all removed. **Still running:** nothing. Every stack is free and the lease is released.
