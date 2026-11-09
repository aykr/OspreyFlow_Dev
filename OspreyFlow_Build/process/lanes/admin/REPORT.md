# admin lane · report · L2.6, the Audit section and Operations' ageing (8–9 November 2026)

Sent back on 9 November by the orchestrator's independent review with six must-fixes and four minor
points. All are done below, each with a test shown red by a plant at its real call site
(`L2.6_RED_RECORD.md`, round 5). The branch is rebased onto main a06d114; the head is in `git log`.

| Brief item | State | Proving test |
| --- | --- | --- |
| 1. Audit read by unit (O2) | met | U1, U2, U7; the picker's writers U19 (live), W9 |
| 1. The rule audit for the Administrator | met | W2–W4, R1–R2; `test_place_routes.py` P1, P2 |
| 1. Filters by who, what and when | met | W8, F1, U2, U6; keyboard K1 |
| 1. Withheld words stay withheld; no account id | met | W1, W6, W10, G4, G5, I1–I9 |
| 2. Operations' ageing (O3) | met; listed only to those who may review | A6, A7; contract C1–C3; keyboard K2 |
| 3. *Promotions overdue* (R7) | alert met; the record left for L3.4 | A1–A5, A8, A9, U5, U20 (live), S1–S6 |
| Keyboard (rule 13) | met | `gates/ac69f9a.keyboard.txt`, 61/61 with `registry.diff` |
| Axe in dark, light and GOV.UK | met | `gates/ac69f9a.axe.txt`, 72/72 |

1. **The picker's writers.** `AuditSectionReader.writers` uses the stream's own unit filter and its `cases`.
   - Live: U19, red with the unit predicate dropped.
   - At the route: W9, red with `cases=True` forced. The route test's fake now narrows the same way the real read does.
2. **Operations' waiting promotions.** `operate_schedules` opens the screen but lists nothing on its own.
   - A promotion is listed only to someone who `may_review` it: one of the dataset's Authors holding `review_promotions`, or an administrator of the dataset's unit. Either way, only someone cleared to the dataset's marking.
   - `test_waiting_promotions_contract.py` is the contract L3.4's store must pass: L3.4 adds its factory to `STORES`. It runs against `ReferenceWaiting` until then, and is red as C1–C3.
   - Recorded in Amendment 6 decision 5 and in the module's docstring.
3. **Governance words withheld.** A source's governance edit no longer serves its handling, its legal basis or what follows from them. W10 is red with them back.
4. **`alerts_for` checks again.** The store keeps each alert's promotion. Each read asks `still` (the sweep's own `_promotion_recipients`), which reads the dataset's unit and marking as they stand now (A11). So a reader who has since been disabled, lost `review_promotions`, dropped below the marking, or moved unit (an administrator or an Author alike, since (j) is withdrawn) is served nothing.
   - Offline: A8, red on 5 of 6 cases (5 of 5 before the Author's move was added). Live: U20 and A8's Author move.
   - L2.7 passes `_promotion_recipients` as `still`.
5. **Records** (`gates/`):
   - `ac69f9a.keyboard.txt`, `ac69f9a.axe.txt`: Playwright on this Mac.
   - `ac69f9a.places.txt`: 104/104 with `places.diff` applied.
   - `0989d88.live.txt`: 26/26 on stack g, plus U19 and U20.
   - `0989d88.ci.txt`, `0989d88.test.txt`.
6. **Minors:**
   - one friction row for the step;
   - `cleared_to` uses `HandlingScheme.clears`;
   - an alert to nobody is not spent: it is counted in `PromotionSweep.unreached`, logged once, and raised once someone may review it (A9);
   - `test_only_the_named_actions_ever_show_their_words`'s docstring says what it checks.
7. **Gates at 0989d88, on main a06d114, offline.** Every failure is explained at the head of each file.
   - `make -k ci`: green except the Docker-backed checks and the test-file wiring. Docker is off on the owner's word (807d070); with Docker up at 05ec788, opentofu and the chart passed.
   - `make test`: 9497 passed, 29 failed, 51 errors:
     - Docker off: 70 refusals;
     - the live tests and their wiring: green live;
     - two place cases until `places.diff` is applied;
     - this machine's `osprey.yaml`, Valkey port and `graphify-out`;
     - main's phone-extraction live test;
     - one preflight case that passes alone (a connect to TEST-NET-1 answered once during the run).
   - The lane's code last changed at e67aed5 (round 6: `may_review`, `_promotion_recipients` and four test files). These offline gates at 0989d88 predate round 6; the orchestrator's merge-time `make -k ci` and `make test` at the merge result stand in for them. Round 6 was run offline (201 passed, plus the two place cases awaiting `places.diff`) and live on stack f (`gates/e67aed5.live.txt`).
8. **Left for L3.4:** the promotion record, `waiting_for_review` passing the contract suite, `all_waiting`, and setting `app.state.waiting_promotions`. **Left for L2.7:** *Needs you* calls `alerts_for(person, lambda p: _promotion_recipients(app, p))`.
9. **Decisions taken** (yours to overrule; all in ADR-145 Amendment 6):
   - (a) words withheld except where the reader's own section shows them;
   - (b) an entry naming no case belongs to its writer's unit;
   - (c) case entries are for `osprey-admin` only;
   - (d) the engines' history needs `read_audit` with `manage_models`;
   - (e) the run ledger is not merged into the stream;
   - (f) the sweep is admin's own lifespan job, and L3.4 sets its source;
   - (g) `read_audit` opens Admin;
   - (h) a start never waits on or drops another start's index build;
   - (i) `grading_change` is filed under *Reads and refusals*, `read_connector_source` under *Loads*;
   - (j), withdrawn at the orchestrator's re-review: it loosened access, so it should have stopped the piece rather than been logged as a decision. An Author grant held by a person of another unit is not one the case recognises (`get_authorized` asks `owning_unit`), so `may_review` now asks the dataset's unit of Authors too (C4, A8).
10. **Requests at the merge:**
    - Apply `places.diff` (two place cases are red without it), `registry.diff` and `ci-wiring.diff`. All three apply cleanly to a06d114.
    - Land `packages/schemas/admin.py` (and its generated types) as a separate schemas commit first.
    - Mark ADR-145 Amendment 6 `written` in `spec/ADR_RESERVATIONS.md`.
    - **Ratify** these files outside admin's map:
      - `services/api/principal_names.py` (`full_names`) with `tests/services/api/test_principal_names.py`;
      - `apps/workspace/keyboard/admin.spec.ts` and `keyboard/admin-harness.tsx`;
      - `tests/services/api/test_place_routes.py`;
      - `apps/workspace/a11y/every-harness.spec.ts`;
      - `services/api/audit.py`;
      - `spec/03_CONDUIT_MIDDLEWARE.md`;
      - `tests/services/api/test_route_rights.py`.
11. **Questions:** none. **Still running:** nothing. Stack g is down and its lease released, the scratch worktree is removed, and no agent is running.
