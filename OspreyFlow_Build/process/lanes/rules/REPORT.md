# rules lane · report · L2.10, one queue, watches, team routing, Raise an alert (9 November 2026; resumed twice, regated at 8e8b9ff)

1. **Team routing, the new rule 3 read: met.** Read in the query, never after it (the queue's list, counts, detail, address and triage writes; a pack's alert item; trends; the rule audit). A routed alert writes no `Alert` node. Red with the check opened at `_routed_sql`: `test_monitoring_queue.py`'s three routing cases and `test_pack_alert_item.py`; trends in the analytics suite; the audit in `test_typology_rules.py` (RED_RECORD §1, §5, §6).
2. **One queue: met.** The inbox's routes and component are gone, and *what fired it* is on the explanation (`alerts/OneQueue.test.tsx`; `test_alert_view_explains_live.py`). **Filters:** the filter case in `test_monitoring_queue.py`, live. **What raises alerts:** `test_team_lead_and_watches.py`.
3. **Watches from the Glass, and G16: met.** *Watch for this* and *Save as a watch*, plus a watched pattern's own schedule. The schedule runs as its owner and is confined to its dataset, red when not confined: a Glass-made watch alerted on `n-elsewhere` (`test_team_lead_and_watches.py`).
4. **The lead's tools: met.** The hand-off, *Suppress until…* and the taken-back marking (`test_team_lead_and_watches.py`, `keyboard/alerts.spec.ts`).
5. **Raise an alert…: met.** It is refused before anything is written: to a Viewer, for a dataset the case doesn't read, for a layer, where there is no home case, and for a drawn item (`test_raise_an_alert.py`, RED_RECORD §2).
6. **The carries: met.** The read path's purge (`test_read_path_purge.py`); the KYC sweep is no longer stopped whole (`test_composite_monitors.py`). `model_limit_reached` is on main since P3. The list picker is left to L2.11, as the brief says; main's new carry (the Lists tab, 4389138) is L2.11's too.
7. **Keyboard, axe, registry: met.** Every new action has its case, red with its handler removed. The registry ids are in `registry-L2.10.patch`. Axe passes in dark, light and GOV.UK.
8. **Gates at 8e8b9ff** (tree 7992ecf2…, rebased onto main at 3be89a7 after the orchestrator's review; `gates/8e8b9ff.*`, `gates/855899f.test.txt`). Closed ports, `OSPREY_LANE` unset. Main moved again afterwards; I did not rebase again, since the lane had gated.
   - **`make -k ci`:** green except the eight `trivy-image-*` scans, `opentofu-check` and `chart-check`. Those need Docker, which is off on this Mac by the owner's choice.
   - **`make test`, on the server** (`stack_lease.sh offline`, at 855899f, code identical to 8e8b9ff): 9,529 passed and 3 failed, each named in the file:
     - `test_valkey_config`, main's own;
     - `test_webapp_preflight`'s GPU case, because the server has a GPU;
     - `test_layout`, tripped by the verb's own folders at the copy's root (since cleared).
   - **`make test` on this Mac** (8e8b9ff): 24 failed and 30 errors, each named: this machine's usual 4, plus 20 failures and 30 errors that need Docker.
   - **`test-js`:** 2,762 of 2,763. The miss is the MatrixView first-frame budget, run under load; it was green re-taken alone.
   - **`glass-a11y`:** 723 passed, every harness in dark, light and GOV.UK.
   - **`glass-keyboard`** (`registry-L2.10.patch` applied uncommitted): 689 passed. ALERTS_ACTIONS and WATCH_PANEL_ACTIONS are covered whole. Two failures are main's own, `boards.spec.ts:225` and its registry check `:423` (the keyboard harness gave the board no grades), fixed in f6def92 on lane/case and carried in CARRIES.md.
9. **Live: the rules lease, stack c, on the server** (`stack_lease.sh remote`), at 855899f, 18:54–19:58Z (`gates/855899f.live.txt`).
   - **Files:** `test_route_rights.py` and the 49 live files the change reaches, now with the analytics suite and `test_typology_rule_routes.py`.
   - **Result:** 779 passed and 1 failed. `test_kyc_rules`' true positive passes.
   - **The one failure was a real defect:** rules' `event_frequency` on ClickHouse. ClickHouse 25.8, the version deployed, refuses a RANGE window offset of 2^31 ms or more, so every frequency span past 24.9 days failed. It hadn't run against a real ClickHouse since stack a went off.
   - **Fixed at 274d114, then 778c4d8,** under its own heading below. The orchestrator ruled that the 779 can stand with the fix's delta. The delta at 778c4d8 (the analytics suite whole, `test_route_rights.py` and the live files that evaluate rules) is `gates/778c4d8.live.txt`: 310 passed, none failed.
   - **Three earlier attempts are recorded as not counted:**
     - the first pass's 122 ClickHouse cases, not run because the stack had no ClickHouse then;
     - a retake orphaned by an ssh drop;
     - a run whose log the verb's prune deleted, a bug fixed on main at dc0b7cd.
   - The lease is released and stack c is down.
10. **Reviews:** two rounds by my own lane-reviewer, and the orchestrator's independent review (b839f81 onward), every finding built and red first (RED_RECORD §5, §8, §9). The ClickHouse fix had two rounds of its own, below.
**A fix to main's own code: ClickHouse `event_frequency` (ADR-133; first seen on main on 7 November, in MORNING).**
- **The defect.** ClickHouse 25.8, the version the deployment pins, refuses a RANGE window offset of 2^31 or more. The adapter's span window was in milliseconds, so every frequency condition with a span past 24.9 days failed in a ClickHouse deployment; ADR-133 allows 366 days. No live run had met a real ClickHouse since stack a went off.
- **First fix (1f04c2c), withdrawn after my lane-reviewer's round.** It was a self-join with two defects: it paired every two events of a subject (n²), and it cut the edge to milliseconds against a microsecond column.
- **Fix (274d114, then 778c4d8).** Each event's running count, non-null amounts and Decimal sum (a RANGE frame with no offset), less the running figures before `at - INTERVAL N DAY`, by an ASOF JOIN on the `DateTime64` itself. Exact to the microsecond, n log n, with `join_use_nulls = 0` set on the query.
- **Both adapters now sum a declared amount as Decimal(38,9)** (778c4d8; the DuckDB adapter changes too), so a total a rule compares is the same on each: 0.1 and 0.2 make 0.3. An amount past that is no amount, never 0. Spec 04 says so.
- **Its case,** at the real call site: a 90-day span with a third event 1 µs either side of the edge, `[±1]`. Red on c's ClickHouse against the old window (refused) and against the self-join (`18.0 == 12.0`); 16 frequency cases green on both adapters.
- **Its lane-reviewer's second round:** the first round's four items closed. Seven more found, each built and red at its real call site (RED_RECORD §12a):
  - the access case was blind to the target branch's check: plants added at the far end, red on both adapters with that check removed;
  - an amount past Decimal128(9) was counted as a present 0;
  - the edge was pinned from one side only;
  - ties were exercised by nothing;
  - `join_use_nulls` was left to the server;
  - the adapters summed differently;
  - the records were uncommitted.
- **The five ClickHouse plants** were red on c, and the DuckDB ones offline.
- **Records:** RED_RECORD §12 and §12a; `gates/274d114.live.txt` and `gates/778c4d8.live.txt`.

11. **Decisions taken** (Prompt L, for the owner to overrule):
    - **Trends:** a routed alert is counted for its team's members alone, not the home case's Authors (the narrower answer).
    - **"My team":** offered only for a rule already saved with it.
    - **Suppress until…:** at most 90 days ahead; the status is unchanged, so it still counts open.
    - **Dataset alerts:** closed by the home case's Authors alone.
    - **A watch's schedule:** daily at 06:00 Europe/London by default.
    - **Watch for this:** reviewed in 90 days.
    - **Addresses:** a dataset or schedule alert's address answers 404 outside its own case, until a later step.
12. **Requests to the orchestrator:**
    - K11's scheduled-run notices need a home in the Studio's schedules (studio).
    - *Raise an alert…* on the selection bar and on a question's answer (case and questions).
    - Apply `registry-L2.10.patch`.
    - Ratify the files outside rules' map, the schemas commit (9b845e0, d8390a6, e382474) going separately and first at merge:
      - the Conduit: `investigations.py`, `recipe_run.py`, `run_resources.py`, `packs.py`, `app.py`'s routes;
      - the analytics adapters and port: `analytics_clickhouse/adapter.py`, `analytics_duckdb/adapter.py` (`event_frequency`, `account_activity`) and `alert_facts.py`; `ports/analytics.py` (`AmountTotalOutOfRange`);
      - the Glass: `App.tsx`, `App.test.tsx`, `inspector/Inspector.tsx`, `patterns/QueryBuilderPanel.tsx`, `patterns/api.ts`, `rights/visibility.ts`, `reports/packText.ts` (rules-b's area, a one-line alert-item change), `a11y/every-harness.spec.ts`;
      - spec 01, 02, 03 and 04, and ADR-133 Amendment 10; `citation_allowlist.txt`;
      - the tests this branch changes (other lanes' among them): tests/conformance/analytics_port/test_suite.py, tests/fixtures/citation_allowlist.txt, tests/ingest/test_alert_evidence_withheld_live.py, tests/ingest/test_kyc_rules.py, tests/ingest/test_typology_rule_routes.py, tests/ingest/test_typology_rules.py, tests/scenarios/ledger_monitoring_support.py, tests/scenarios/pid_monitoring_support.py, tests/scenarios/test_phase7_stage6c_watch_routes.py, tests/services/api/test_alert_evidence_withheld.py, tests/services/api/test_alert_node_marking.py, tests/services/api/test_alert_queue_counts.py, tests/services/api/test_alert_runs_partly_raised.py, tests/services/api/test_alert_view_explains_live.py, tests/services/api/test_alert_view_explains.py, tests/services/api/test_composite_monitors.py, tests/services/api/test_evaluation_touched_nodes.py, tests/services/api/test_evaluation.py, tests/services/api/test_investigation_levels.py, tests/services/api/test_load_records.py, tests/services/api/test_monitoring_queue.py, tests/services/api/test_monitors.py, tests/services/api/test_pack_alert_item.py, tests/services/api/test_place_routes.py, tests/services/api/test_raise_an_alert.py, tests/services/api/test_read_path_purge.py, tests/services/api/test_recipe_run_path.py, tests/services/api/test_revert_closes_alerts.py, tests/services/api/test_route_rights.py, tests/services/api/test_run_resources.py, tests/services/api/test_sentence_rules.py, tests/services/api/test_team_lead_and_watches.py.
    - The ADR-146 Amendment 4 reservation.
13. **Questions for the owner:** none open. Q3 was ruled (a), as Amendment 4 point 9.
14. **Commits** (rebased onto 3be89a7):
    - schemas: 9b845e0, d8390a6, e382474;
    - the Conduit: c80fbe9;
    - the Glass: 93e8786;
    - keyboard: a214218;
    - review rounds: 18dc869, then b839f81, 9c11cb8, 396c45b, 7bed439, c98052b and 5c81b0b;
    - live and test reds: 4eaceff, 01af58e, 38ca288, 8e8b9ff;
    - spec: 8b73b8c, 3189839, 47327ec, 44c02cd;
    - ci fixes: 51e5bdd, e1bd6a3, bbe22ba, 148b381;
    - records: a513b6e, 6263f6b, 7aef8ba;
    - the gates at 8e8b9ff: aef9bb2, 412f893, 855899f;
    - the ClickHouse fix: 1f04c2c, then 274d114 and 778c4d8 after two review rounds;
    - the live and server records: 3b6ed0e, then the deltas at 274d114 and 778c4d8 with this report;
    - then this report and the friction row.
15. **Still running:** nothing. The lease on c is released, its stack is down, and no server run is alive.
