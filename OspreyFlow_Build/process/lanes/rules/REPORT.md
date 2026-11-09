# rules lane · report · L2.10, one queue, watches, team routing, Raise an alert (9 November 2026; resumed session)

1. **Team routing, the new rule 3 read: met.** Read in the query, never after it (the queue's list, counts, detail, address and triage writes; a pack's alert item; trends; the rule audit). A routed alert writes no `Alert` node. Red with the check opened at `_routed_sql`: `test_monitoring_queue.py`'s three routing cases and `test_pack_alert_item.py`; trends in the analytics suite; the audit in `test_typology_rules.py` (RED_RECORD §1, §5, §6).
2. **One queue: met.** The inbox's routes and component are gone, and *what fired it* is on the explanation (`alerts/OneQueue.test.tsx`; `test_alert_view_explains_live.py`). **Filters:** the filter case in `test_monitoring_queue.py`, live. **What raises alerts:** `test_team_lead_and_watches.py`.
3. **Watches from the Glass, and G16: met.** *Watch for this* and *Save as a watch*, plus a watched pattern's own schedule. The schedule runs as its owner and is confined to its dataset, red when not confined: a Glass-made watch alerted on `n-elsewhere` (`test_team_lead_and_watches.py`).
4. **The lead's tools: met.** The hand-off, *Suppress until…* and the taken-back marking (`test_team_lead_and_watches.py`, `keyboard/alerts.spec.ts`).
5. **Raise an alert…: met.** It is refused before anything is written: to a Viewer, for a dataset the case doesn't read, for a layer, where there is no home case, and for a drawn item (`test_raise_an_alert.py`, RED_RECORD §2).
6. **The carries: met.** The read path's purge (`test_read_path_purge.py`); the KYC sweep is no longer stopped whole (`test_composite_monitors.py`). `model_limit_reached` is on main since P3. The list picker is left to L2.11, as the brief says; main's new carry (the Lists tab, 4389138) is L2.11's too.
7. **Keyboard, axe, registry: met.** Every new action has its case, red with its handler removed. The registry ids are in `registry-L2.10.patch`. Axe passes in dark, light and GOV.UK.
8. **Gates at faf47b4** (tree 2c2cc7573935951767cb1415bfcde4bead80690a), rebased on main at 7783935, offline, closed ports, `OSPREY_LANE` unset (`gates/faf47b4.*.txt`). Main has since moved only by two records (4389138, 451a648), so I did not rebase under the gates.
   - **`make -k ci`:** green bar the seven `trivy-image-*` scans (Docker Hub, 429).
   - **`make test`:** 9,156 passed, 4 failed and 2 errors. The failures are this machine's usual four: `osprey.yaml`, the closed-port Valkey, `graphify-out/` at the root and the phone fixture's object store. The 2 errors are `test_workspace_proxy`'s nginx pull (429).
   - **`test-js`:** 2,753 of 2,754. The miss is the MatrixView first-frame budget, run under load; it was green re-taken alone.
   - **`glass-a11y`:** 683 passed. **`glass-keyboard`** (the patch applied uncommitted): 680 passed and 1 skipped.
9. **Live (rules lease, stack a, at faf47b4, 06:07–06:54Z):** `test_route_rights.py` and every live file the change reaches, 47 files. 512 passed and 3 failed:
   - `test_kyc_rules`' true positive, red on main since L2.8c;
   - the address timing case, run beside `test-js` and keyboard on a newly recreated stack;
   - `test_alert_evidence_withheld_live`'s `_pending` helper. It unpacked the repoint journal's pairs as two values, but since D3 they are `(old, new, old_type)` triples. It only passed when the shared table happened to hold no other run's pair. Fixed, with its red by plant at `_close_record`; the retake alone is appended to the live file.
10. **Reviews:** one round by my own lane-reviewer (`5135b0c`), every finding built and red first (RED_RECORD §5). This is a new rule 3 read, so the orchestrator's independent review is due.
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
    - Ratify the files outside rules' map: `App.tsx`, `App.test.tsx`, `inspector/Inspector.tsx`, `patterns/QueryBuilderPanel.tsx`, `rights/visibility.ts`, `reports/packText.ts` (rules-b's area, a one-line alert-item change), `a11y/every-harness.spec.ts`, `packs.py`, `analytics_duckdb/alert_facts.py`, the analytics suite, `test_route_rights.py`, `test_place_routes.py`, spec 01, 02 and 03, `citation_allowlist.txt`.
    - The ADR-146 Amendment 4 reservation.
13. **Questions for the owner:** none open. Q3 was ruled (a), as Amendment 4 point 9.
14. **Commits:** c284fbd schemas; 5774082 api; d93e487 workspace; 9268386 keyboard; 5135b0c review; 5c17d21, 29e03e5 and faf47b4 live and test reds; 12e9b7a, 5b76a7c spec; bf76713, 515d9cb, f609831 ci fixes; 38c890d the earlier live run; then the gates, the evidence helper's fix and this report.
15. **Still running:** nothing. The lease is released and the stack is down.
