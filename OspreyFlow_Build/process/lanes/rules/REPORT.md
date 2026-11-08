# rules lane · report · L2.9, four places: Rules and Monitoring, /alerts/<id>, the way back (8 November 2026; after three own review rounds and two of the orchestrator's)

1. **Rulings:**
   - **The owner's ruling on Q1 (a), relayed by the orchestrator, 8 November:** the *Rule author* gains `read_alert_queue`, since whoever triages must read the queue. ADR-112 Amendment 5 decision 2's list is amended in ADR-146 Amendment 2 point 5. The change is in `rights.py`'s `RULE_AUTHOR`, in the branch's schemas commit. ADR-112 Amendment 5's test "Rule author opens Rules and Monitoring" is a passing test now, no longer an xfail; it is red on the role without the right, and so is `test_rights.py`'s Rule author case. The role is offered Rules and Monitoring and the Glass (whose Home reads the same queue), never the Studio; the orchestrator agreed.
   - **`needs` kept, the orchestrator agreeing:** it was asked to be dropped as interim. It is not interim: it is ADR-145 Amendment 1's entry-read rule, and the Rule author now passes it. Dropping it would offer the place to a custom role holding `triage_alerts` alone, whose first screen refuses it, and `places.test.tsx` would go red against `placesByRole.json`.
   - **The orchestrator's ruling (a) on its review's item 4:** the queue's rows go only to whom the place is offered and to the Reports Viewer, who keeps ADR-145 Amendment 4 decision 10's list and has no way into an alert's detail. Any other reader of the queue (the Data Engineer) gets counts. Within accepted ADRs; recorded in Amendment 2 point 3. I stopped item 4 as first written because it contradicted decision 10.
   - Q2 (a), the orchestrator's settlement: the Data Engineer's and the Administrator's losses are as in ADR-146 Amendment 2 point 2.
   - Decisions taken:
     - Held rows are shared with the Studio's Runs.
     - Connection strength stays in the Glass, under More.
     - `/rules` is the place's address.
     - The view is named "From alert: ‹title›".
     - The address's refusals are equalised in time by a quantum (250 ms), not by identical reads, which no missing id can make (ADR-146 Amendment 2 point 6).
     - The queue's rows go to the Reports Viewer by its role, not a right, so a custom role copied from it gets counts, the narrower answer.
2. **The fourth place: met.**
   - R&M is in the switcher and the GOV.UK header, with the open-alert count. It is offered for `triage_alerts` or `author_rules`, together with the queue's read (`places.json` `needs`).
   - Every route of the place asks for the place's gate after its own right. The gate asks for the place's `needs` (`read_alert_queue`) as well as an opening right, so the routes refuse exactly whom the place is not offered to. The five exceptions are shared outside it: three reads (the queue's rows and its counts, held rows' list) and two writes (held rows' reject and release).
   - Its tabs are Alerts, What raises alerts, Held rows and Changes.
   - Tests: `test_place_routes.py`, red with the gate taken off `deploy_typology_rule`, with the gate open to all, with an unplaced rule route, and (review round 2, item 3) with the gate asking for an opening right alone: a `triage_alerts`-only holder, directly or through a custom role, then reached past their checks at the eight triage routes. Also `places.test.tsx`, `keyboard/shell.spec.ts` and `rules-place.spec.ts`.
   - The queue's rows (item 4): `test_alert_queue_counts.py`, red with the rows' check removed (the Data Engineer was answered every row, words and all); Home's counts in `homeData.test.ts`, red with the fallback removed.
3. **Monitoring leaves the Glass: met.** The banner is Case · Boards, and Connection strength moves under More. The count is unchanged at 24 (`App.chrome.test.tsx`).
4. **`/alerts/<id>`: met.**
   - `GET /v1/alerts/{id}` scopes the reader to the alert's case before reading. Seven cases a reader may not see answer exactly as a missing alert (`test_alert_address.py`; the reds were re-taken in RED_RECORD §6).
   - A History-API router; Home's rows open the alert; an address is ignored for whoever the place is not offered to.
   - **Answered at the same time** (review round 2, blocker 1): every refusal waits to the end of its 250 ms quantum. Red with the wait removed (a fake clock: 2, 2 and 17 ms). Live, under the rules lease on stack c: without the wait, missing 4.5 ms, another case 4.4 ms, hidden 100.8 ms (max 176.6 ms); with it, 253.3, 253.1 and 253.7 ms (`l2.9/address-timing.txt`).
   - Live through the real app, `get_principal`, `PostgresAlertStore.case_of` and ArcadeDB (`test_alert_address_live.py`, review round 2, blocker 2): the alert answered in its case, and its three refusals alike byte for byte. Hermetic additions: a team-shared alert answered, and a read-only layer answered only to a reader of the original, each red.
   - B14 is at the alert's address (spec 08), with its refusal in process and over the wire.
5. **Open the evidence: met.**
   - It saves a private view of the case and opens L3.2b's lens with *← Back to the alert*, which returns to the same alert, still open.
   - It saves into the case the alert was read in, refused in words when that is not the case open or the address names another (`evidenceCase`, review round 2, item 6; red with either check removed).
   - A failure is said on the alert alone. Round 3 found a stale "could not be opened" left over the Glass; it is fixed, with the red first (RED_RECORD §8).
   - Tests: `App.test.tsx` and `rules-place.spec.ts`, each red.
6. **Keyboard and axe: met.** Every new action has its case, and its registry id is in `registry-L2.9.patch`. Axe passes in dark, light and GOV.UK.
7. **Gates at 298315a** (tree eb4bbf855545c5c6817de9aadad2332e17de3fda), rebased on main at 47b0bc4 (after studio's L1.4), offline, with closed ports and `OSPREY_LANE` unset (`gates/298315a.*.txt`):
   - **`make -k ci`:** every target green except the seven `trivy-image-*` builds, refused by Docker Hub (429 Too Many Requests). Environmental.
   - **`make test`:** 8,714 passed and 4 failed, all this machine's own, the same set as at 6c5db53 and 570fdf1:
     - `osprey.yaml` names `osm-local-great-britain`;
     - the closed-port `VALKEY_PORT` is exported;
     - `graphify-out/` sits at the root;
     - the phone fixture needs an object store.
   - **`test-js`:** 2,717 of 2,718. The miss was the MatrixView first-frame budget, a timing case run under load, untouched here; alone it is green.
   - **`glass-a11y`:** 573 passed.
   - **`glass-keyboard`,** with `registry-L2.9.patch` applied uncommitted: 613 passed, 1 skipped and 2 failed, both in studio's `ingest-studio.spec.ts`. One was a 5 s poll under load, the other its coverage case after the worker restarted. Re-taken alone: 46 passed.
8. **Live (rules lease, stack b, at 298315a, 22:54–22:59Z):** 25 suites, the 18 earlier ones plus every live file the change reaches. 1,597 passed and 4 failed, each explained (`gates/298315a.live.txt`):
   - P2's two model routes are missing from `ROUTE_RIGHTS` on main (platform has it).
   - The shared database's leftover rules break the rule list (L2.8d's record).
   - The Phase 8 in-process walkthrough is red on main before B14: a `loader` token holds no `create_case` (fixed here), then B4 seeds into a case of one dataset (not this step's). B14's address is proven live by `test_alert_address_live.py` instead.
   - Stage 6c's 250th-node case drew a number from a pool of 100 that an earlier node held. Re-taken alone, it passed and two other ingest cases hit MinIO's `INTERNAL_FAILURE`; B14's own case in that file passed both times. Environmental.
   - **Not run:** the over-the-wire tier needs a rendered deployment of this branch. The only one is the owner's, which lanes do not rebuild. For the orchestrator, at the merge or on D2's rebuilt deployment.
9. **Reviews:** three rounds by my own lane-reviewer.
   - Round 1: 8 must-fix and 4 minor.
   - Round 2: 4 must-fix and 7 minor.
   - Round 3: no code must-fix. Its must-fix items were this report and the gates. Minor 3 (the stale problem) is fixed; the "two shared reads" wording and a keyboard case's title are corrected; the rest are in item 13.
   - The orchestrator's independent review, round 2: 2 blockers, 4 must-fix and 4 minor. All are built here (item 4 as ruled), each red first (RED_RECORD §9). Item 5 (case rebases onto my `App.tsx`) and item 9 (the reservation title) are the orchestrator's.
10. **Questions for the owner:** **Q3** (ADR-146 Amendment 2 point 6). An alert whose evidence takes longer than one quantum to read is refused on a later quantum, so it alone can still be told apart from a missing id. The measured worst case here is 177 ms against 250 ms. Options:
    - (a) accept it, recorded; recommended, since it applies only to alerts with unusually large evidence;
    - (b) cap the evidence an alert may cite, and size the quantum to read the cap;
    - (c) a larger quantum.
    Until the owner rules, the guarantee is the one measured, no wider. Found on the way, already on main and not this step's: the queue's own list reads the evidence of every alert in the case, hidden ones included, so its time grows with them.
11. **Ratify (outside rules' map):**
    - Case lane: `views/ViewLensBanner.tsx` and `views.css`, and the jump tests removed in `test_case_writes`, `test_case_domains` and `test_drawn_datasets`.
    - Shell and harness:
      - `App.tsx`/`App.test.tsx`, `rights/visibility.ts`, `assessment/api.ts`, `watches/AlertInbox.tsx`, `watches/api.ts`.
      - The keyboard specs and harnesses, and `a11y/every-harness.spec.ts`.
      - `live/capture-kit.ts`/`pid-capture.spec.ts`; the captures will need retaking.
    - Conduit and tests:
      - `app.py`, `history_labels.py`, and `packages/schemas` (`AlertAtAddress`, `AlertQueueCounts` and `rights.py`'s `RULE_AUTHOR`, in their own commit).
      - `tests/schemas/test_rights.py`, `test_route_rights.py` and `test_investigation_levels.py` (the counts route's rows).
      - The scenario tests, including the Phase 8 walkthrough's analyst-who-loads token, and the other jump-test lists.
      - `OspreyFlow_Build/Makefile` and `.github/workflows/ci.yml`, for the new live file.
    - Spec: 01, 02, 03, 08 and the 06 append.
12. **Requests:**
    - Commit `registry-L2.9.patch` at the merge.
    - Mark ADR-146 Amendment 2 `written`.
    - Run the over-the-wire tier at the merge, or on D2's rebuilt deployment.
    - Platform: add P2's `models_admin_limits_route` and `models_admin_usage_route` to `test_route_rights.py`'s `ROUTE_RIGHTS` (passed on by the orchestrator).
    - Docs lane: the user guide's "Jump into investigation", and the PID captures.
    - Case lane: the dead `refuse_copying_a_drawn_dataset`/`read_the_same_dataset`.
13. **Left, minor:**
    - Some stale jump prose remains in schema docstrings.
    - The harnesses mirror App's wiring; App.test covers the real wiring.
    - A superseded `openLens` leaves the address with no lens open (round 3, minor 4).
    - `PostgresAlertStore.case_of` is reached only by B14's live run (round 3, minor 5).
    - B14's over-the-wire step checks that the node list is not empty, not that it holds the referents (round 3, minor 6).
    - The Phase 8 in-process walkthrough is red on main at B4 (one dataset per case); it is not this step's.
14. **Commits:** main..HEAD, 29 with this one. The `wip(rules)` rewrite was not needed: the paused session left only proper commits, plus an uncommitted `HANDOFF.md` and two partial gate files, all removed. **Still running:** nothing. Every stack is free and the lease is released.
