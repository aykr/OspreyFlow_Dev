# Rules lane · L2.10 · red record (9 November 2026)

Each test below was run green, then red with one plant at its real call site, then green again with
the plant removed (rule 15). Offline runs were on the closed ports with `OSPREY_LANE` unset; the
Postgres runs (§1) were under the rules lease on stack b.

## 1. Team routing, the new rule 3 read (live, rules lease, stack b)

- **The check opened.** Plant: `_routed_sql`'s first clause `routed_team IS NULL` read as `true`,
  its parameters kept (`alerts.py`). Red: in `test_monitoring_queue.py`,
  `test_a_team_routed_alert_reaches_only_its_members_and_the_home_cases_authors`,
  `test_a_member_leaving_the_team_no_longer_reads_its_routed_alert` and
  `test_without_an_answer_for_its_datasets_a_routed_alert_reaches_its_team_alone`; in
  `test_pack_alert_item.py`, `test_an_alert_routed_to_a_team_is_withheld_in_a_pack_from_a_reader_outside_it`
  (`201 == 404`: the non-member could add it). All 27 other cases green.
  - A first plant replaced the whole clause with `true`. That dropped parameters the query still sends,
    so every queue case errored. It was red for the wrong reason and was discarded (rule 15's second
    lesson).
- **The Authors' clause read for any dataset.** Plant: `dataset_id = ANY($authored)` read as
  `cardinality($authored) > 0`. Red: the routing case only (an Author of another dataset's home case
  read the alert).
- **A pack's own check.** Plant: `packs.readable` keeps every cited alert whatever `routed_readable`
  answers. Red: the pack case (`(False, [the item]) == (True, [])`).
- **Trends** (the analytics suite, DuckDB, offline).
  - Plant: the owner clause back to `audience <> 'case'`. Red:
    `test_a_team_routed_alert_is_counted_for_the_teams_members_alone` (`deployer.events 2 == 1`).
  - Plant: the routed clause removed. Red: the same case, for the member.
- **No Alert node.** Plant: `writes_no_alert_node` reads `is_just_me` alone. Red:
  `test_sentence_rules.py::test_a_sentence_routed_to_a_team_names_it_and_writes_no_alert_node` (the fake
  graph refuses the write, so no alert).

## 2. Raise an alert… (offline)

- Plant: the drawn-item check off. Red: `test_a_dataset_alert_citing_a_drawn_item_is_refused_at_the_route`.
- Plant: the dataset-read check off. Red: `test_a_dataset_the_case_does_not_read_or_with_no_home_case_is_refused[not-read-by-the-case]` and `[a-layer]`.
- A Viewer's refusal is the route's own level check (`InvestigationEditorDep`), proved by `test_a_case_the_raiser_may_not_write_is_refused`.

## 3. The carries (offline)

- **The read path's purge.** Plant: the purge in `settle_repoints` skipped. Red:
  `test_read_path_purge.py::test_a_settle_on_a_read_path_purges_the_copies_it_re_marked_at_once`.
- **The sweep's per-customer catch.** Plant: it catches `ZeroDivisionError` alone. Red:
  `test_composite_monitors.py::test_one_failing_rule_never_stops_the_daily_sweep_whole`
  (`RuntimeError: a read refused` stopped the sweep).
- **A row without its node outside a load.** Plant: `RuntimeError` let through. Red:
  `test_alert_node_marking.py::test_after_a_commit_an_unreadable_referent_node_raises_the_row_without_its_node`.
  This test replaces `…_still_raises_as_today`, which held the old behaviour the carry asked to change.
- **Part-way failures.** Plant: the `PartlyRaised` catches in `rule_schedule.py` and `screening_refresh.py`
  read as `ZeroDivisionError`. Red: `test_alert_runs_partly_raised.py`'s slot and re-screening cases.

## 4. The Glass

- **Ask to search's `model_limit_reached`.** Red before the change in `patterns/api.ts`:
  `api.test.ts` "says a model's limit is reached in the Conduit's own words". On main since P3's merge,
  so this lane's copy drops at the rebase.
- **Keyboard (rule 13).**
  - Plant: the suppress handler made a no-op. Red: `keyboard/alerts.spec.ts` "a team's lead suppresses
    one of its alerts…".
  - Plant: the raise handler made a no-op. Red: `keyboard/watch-panels.spec.ts` "an alert is raised to
    the dataset, by keyboard".
  - The other new cases each assert the server received the call.
- **Axe.** `monitoring-harness.html open=a-team` was first red on 2.5.3: the visible label "Older than
  … days" was split around its field. It now reads "Older than, in days", its name the same. Green in
  dark, light and GOV.UK, as is `watch-panels-harness.html`, which now applies the brand.

## 5. The lane-reviewer's round (offline unless said)

- **The rule audit read a routed firing (finding 1).** The fix: `rule_holds.readable_rule_audit` asks
  `routed_readable`. Its test, `test_typology_rules.py::test_a_routed_alerts_firing_is_withheld_from_the_rule_audit_outside_its_team`,
  is live, run under the lease in the second pass (§6).
- **`test_team_lead_and_watches.py`.** Each case was red with one plant at its real call site:
  - `answers_for_datasets` asking `is not None` for Author;
  - `leads_today` not asking `acting_lead`;
  - `suppress` without its lead check;
  - `assign` without its lead check;
  - the dataset alert's `closer` failing open;
  - the schedule's owner not confined to the watch's dataset (two cases: the Glass-made watch alerted
    on `n-elsewhere`);
  - the claim not given back on an unreachable identity provider;
  - `runs_for_reader` returning the runs as stored.
- **The composite sweep in the brief's shape.** Plant: `raise_committed`'s `CompositeReadOnlyError`
  catch removed. Red: `test_composite_monitors.py::test_an_alert_refused_its_node_in_a_composite_case_still_raises_and_the_sweep_goes_on`.
  The unresolved deployer is `test_a_rule_whose_deployer_cannot_be_resolved_is_said_in_its_audit`.
- **The filters and a dataset alert's reach** are live (`test_monitoring_queue.py`'s two new cases), run
  in the second pass.

## 6. The second live pass (rules lease, stack b, a75bbb8, 01:36–02:13Z), and after

- 511 passed and 4 failed in the same 47 files:
  - the filter case: its alerts used the fixture's fixed date, and its helper passed `today` twice; both
    fixed and green;
  - the address's timing case: the hidden alert's worst was 253.9 ms against its 250 ms quantum, while
    `make ci` ran beside it. That is L2.9's Q3 residual, still the owner's. It passed when re-taken
    alone;
  - two cases that fail on main and are not this step's: `test_kyc_rules.py`'s true positive (red since
    L2.8c, `gates/47435fa.live.txt`), and the repoint journal case, which reads another test's
    leftover records and passes alone.
- **Reds taken under the lease after the pass.**
  - The suppressed clause in `list_queue` opened. Red: the filter case.
  - The rule audit's routing check removed. Red:
    `test_typology_rules.py::test_a_routed_alerts_firing_is_withheld_from_the_rule_audit_outside_its_team`.
  - The dataset alert's clause admitting nothing. Red: its reach case.
- **A plant that stayed green.** The dataset clause widened to every dataset. The reach clause every kind
  shares already keeps the alert out of a case on another dataset, so the plant proved nothing (rule
  15). The test now says so.
- **Keyboard (with the registry patch applied, uncommitted).** 667 passed, 1 skipped and 2 failed, both in
  `ingest-studio.spec.ts`. They were mine: the sentence builder read the team list from a harness
  answering something else, which stopped the Studio's Checks on load. Fixed (`221d489`), and the spec
  is green alone (46).
- **Axe.** 650 passed.
