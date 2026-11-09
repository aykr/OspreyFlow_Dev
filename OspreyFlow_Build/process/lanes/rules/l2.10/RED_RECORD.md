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

## 7. The live run at faf47b4, after the rebase (rules lease, stack a, 06:07–07:07Z)

- `test_alert_evidence_withheld_live.py`'s `_pending` read every record in the shared table and unpacked
  each link pair as two, but since the journal's D3 round a pair is `(old, new, old_type)`. It passed
  only while no other run's pair was in the table. Its fix reads a pair's first two fields. Plant:
  `AlertStore._close_record` a no-op, so the settle applies the repoint (the queue's assertions hold)
  and keeps the record. Red at the last assertion alone (`[(link, revision)] == []`), green with the
  plant removed, and the file whole green alone (38).
- The address's timing case was red beside `test-js` and keyboard on a newly recreated stack (hidden
  median 1,415 ms). It was green re-taken alone under the same lease; this is the Q3 residual as ruled.

## 8. The orchestrator's review round (9 November 2026)

Each case was green, red with one plant at its real call site, and green again with the plant removed.
Offline runs used the closed ports; the live ones ran under the rules lease on stack c, 07:39–07:40Z, at
e79271b.

- **Item 1, `GET …/alert-sources` (live).** One case:
  `test_monitoring_queue.py::test_what_raises_alerts_lists_only_the_readers_watches_and_counts_only_what_they_may_see`,
  through `read_alert_sources` over the real stores. Its plants, and what each turned red:
  - `HotlistStore.list_authorized`'s owner clause read as `$1::text IS NOT NULL`: another's hotlists were listed;
  - `_routed_sql`'s first clause read as `true`, its parameters kept: the routed rule counted 2 for the non-member;
  - the route counting from `list_queue`'s rows, not the reader's queue: the alert citing a hidden node was counted (2 == 1).
- **Item 2, `GET …/alert-teams` (offline).** One case:
  `test_team_lead_and_watches.py::test_the_teams_a_rule_may_go_to_list_members_to_the_lead_alone`.
  - The members' lead check read as true: team-7's lead was told team-8's member.
  - The no-right guard removed: the Reports Viewer was told both teams.
- **Item 3, names (offline).**
  - `test_what_raises_alerts_names_its_people_and_asks_for_no_one_else`: red with `people_named`
    leaving the suppressors out.
  - `OneQueue.test.tsx` "names the owner and the suppressor…": red with the panel showing `owner`
    (the id), 2 == 3.
- **Item 4, a watch whose owner has lost its dataset (offline, through the app's own
  `owner_reaches_dataset_in`).**
  - The schedule's reach check removed: the owner, narrowed to ds-1, alerted on n-mine.
  - The load path's reach check removed: the owner was matched in all three evaluations.
- **Item 5 (live).** `test_monitors.py::test_a_watchs_schedule_is_set_by_its_owner_alone`, red with
  `set_schedule`'s owner clause read as `$2::text IS NOT NULL` (DID NOT RAISE).
- **Item 6, keyboard.** Each new case drives a select by typing its label and a date by its segments.
  Each was red with its handler removed. Where a plant made a controlled select a no-op, the first red
  was the value check, so the send was also planted:
  - the tab's hotlists panel removed: the Hotlists heading was not found;
  - the whose filter's `onChange` a no-op: the value check; with `show` dropped from the request: the request assertion;
  - the hand-off's `onClick` a no-op: the assign request;
  - the column filter's `onChange` a no-op: Deposits still shown;
  - the team choice's change dropped: the value check; with `team_id` dropped from the sentence: the sentence assertion;
  - the schedule's `onChange` a no-op: the value check; with the schedule sent as daily: the value check again, since the select shows the server's answer;
  - *Watch for this*'s call removed: the hotlist request;
  - *Save as a watch*'s call removed: the monitor request.
  - The suppress and raise cases are §4's.
- **Item 7 (live).** The kyc true positive is now proposed by one person and approved by another.
  Red with `approve_close` closing through `set_queue_triage` without `_close`: the match stayed
  inferred. The case's first green run errored with an `httpx.ReadError` while the stack's ArcadeDB
  was still coming up; it passed in the plant run and in the green run after.
- **Item 9 (offline).** `test_a_routed_alerts_explanation_names_the_team_it_was_routed_to`, red with
  the explanation reading `alert.team` (unit-1).

## 9. My lane-reviewer's two rounds on the fix (9 November 2026)

Each case was green, red with one plant at its real call site, and green again with the plant removed.
Offline runs used the closed ports; the live run was under the rules lease on stack a, 07:58–07:59Z,
at ef45fa1.

- **The scheduled and folder-watched runs' reach.**
  `test_recipe_run_path.py::test_a_scheduled_run_checks_a_watchs_owner_reach_through_the_states_own_stores`.
  Its state holds the stores and no `watch_reach`, as the running Conduit's does. Red with
  `from_state`'s building of `watch_reach` removed: `None is not None`. The test before it had handed
  the state a `watch_reach` the real one never has, which is why the gap went unseen; it now leaves
  the built field out.
- **The hotlist path.** `test_evaluation_touched_nodes.py::test_a_hotlist_whose_owner_has_lost_its_dataset_matches_nothing`.
  - With the reach check removed from the hotlist loop: the owner, narrowed to the dataset, was
    given the match three times.
  - With the per-watch catch removed from `_within_its_dataset`: the failing check stopped the
    evaluation whole (`ConnectionError`), where it now stops that hotlist alone and a second one
    still matches.
  - Each refusal is asserted in the log.
  - The fakes of the case store take `need` as the real one does, required, and assert it is
    Viewer.
- **The hand-off's names.**
  - `test_the_teams_a_rule_may_go_to_list_members_to_the_lead_alone`, red with no member names
    served (`{} == {...}`).
  - `OneQueue.test.tsx`'s lead case, red with the options shown by id (no option "Mo Member").
  - `keyboard/alerts.spec.ts`'s hand-off, red the same way (no option "Priya Shah").
  - A first keyboard run without the name assertion stayed green under that plant, because typing a
    label works whatever the label says, so the assertion was added.
- **The kyc false positive (live).** It is now closed by a second person before it is judged. Red
  with `_close` confirming a false positive too: Nair's match was asserted. Green before and after.
- **`writeTheSentence` by keys.** Red with the Frequency select's `onChange` a no-op (the value
  check). A first plant on the Subject select stayed green: Person is its default, so choosing it
  changes nothing. The plant proved nothing and was replaced (rule 15).

## 10. The gate's own finding (make test at 5798919)

- `test_run_resources.py`'s two coverage cases were red at the gate: the command-line builder gave
  `run_deps()` no `watch_reach`, so a command-line load would have matched no watch with a dataset.
  That was the fail-closed gap Amendment 4 had recorded, and the existing test, which asks that every
  field a run needs is given, found it. `RunResources` now holds the case store and builds the check
  over it and the dataset store, and both cases are green. The same `make ci` run found an unused
  `type: ignore` in `app.py`, now removed.

## 11. The live set at 0ba0254 and its re-takes (rules lease, stack a)

- **The set, 10:11–10:45Z.** 515 passed and 2 failed, both stage 6c's hotlist cases
  (`test_phase7_stage6c_watch_routes.py`). Their owner held no level on any case reading the
  hotlists' dataset, so Amendment 4 point 7's reach check refused them, as it should. That was the
  test's shape, not the product's: a hotlist made with *Watch for this* is made from a case. The cases
  now give the owner a case of their own reading the dataset, and both pass (re-take, 10:51Z). Their
  red is the set's own run, which had no such case.
- **`test_typology_rule_routes.py`'s rule list (red on main).** The list holds every deployment-wide
  sentence (ADR-133 decision 1), and the shared stack holds other runs' sentences. The case is now
  judged by its own rules, and another case must never list them. Red with `list_for_case`'s case
  clause read as `$1::text IS NOT NULL`: another case listed this one's rule.
- **The address timing case.** It passed in the set and again re-taken alone.
- **Not rules': PID r1 and r14's interval cases.** These are the PID build's. The loaded `valid_from`
  keeps the row's time of day where the plan expects the day's start. Sent to the orchestrator.

## 12. The live set at 855899f: the ClickHouse frequency span (stack c, on the server, 9 November 2026)

The live retake at 855899f (`gates/855899f.live.txt`, 779 passed, 1 failed) was the first in which the analytics suite's
`analytics_clickhouse` variant ran against a real ClickHouse: the stacks had none until c's on 18125. That ClickHouse is
25.8.33.6, the version the deployment pins (`harness/render.py`). The failure was
`test_frequency_counts_the_most_events_in_any_span_of_the_days_asked[analytics_clickhouse]`, at its 30-day span:
ClickHouse refuses a RANGE window offset of 2^31 or more ("Frame start offset for 'RANGE' frame must be a nonnegative
32-bit integer, '2592000000' of type 'UInt64' given"). So `event_frequency` failed in a ClickHouse deployment for any
span past about 24.9 days (ADR-133's frequency conditions allow 366).

- **The first fix (1f04c2c), withdrawn after my lane-reviewer's round.** It was a self-join, `b.at BETWEEN a.at - span_ms AND a.at`,
  with two defects:
  - it paired every two events of a subject, n² with no bound;
  - it kept the old window's milliseconds against a column of microseconds (`DateTime64(6)`), so an event up to 999 µs
    outside the span was counted, where DuckDB does not count it.
- **The fix** (`analytics_clickhouse/adapter.py`): each event's running count, non-null amounts and Decimal sum up to and
  with its instant, read through a RANGE frame with no offset (UNBOUNDED PRECEDING to CURRENT ROW, ties included).
  - It subtracts the running figures of the last instant strictly before `at - INTERVAL N DAY`, by an ASOF JOIN on the
    `DateTime64` itself. That is exact to the microsecond, and sorting rather than pairing, so n log n.
  - Amounts are summed as `Decimal128(9)` from their shortest text, so the subtraction is exact (0.1 + 0.2 sums to 0.3).
    An amount of 10^29 or more reads as no amount.
  - No per-row key is needed (the review's third item).
- **The case**, at the real call site, the span 90 days:
  `test_frequency_over_a_span_past_twenty_five_days_keeps_its_edge_to_the_microsecond[±1]`. A third event 1 µs more
  than 90 days after day 90 is in no span with it (largest total 12); 1 µs less, it is (18).
- **Red, each on c's ClickHouse, the rules lease, through `stack_lease.sh remote`:**
  - Plant 1, the RANGE window on milliseconds (8e8b9ff's): three cases red, each refused by ClickHouse
    (offsets 2592000000 and 7776000000).
  - Plant 2, the self-join on milliseconds (1f04c2c's): `[1-12.0]` red, `assert 18.0 == 12.0`.
  - The fix: 16 passed, both adapters.
- **Green, the whole analytics suite on both adapters:** `gates/274d114.live.txt`. It includes
  `test_an_event_the_author_may_not_see_adds_nothing_and_is_never_a_first`, the rule 3 case on this read.

### 12a. My lane-reviewer's second round on the frequency fix (778c4d8)

It closed the first round's four items and found seven more. Each is built, red first, at its real call site.

1. **The access case did not reach the target branch's check.** Every hidden plant had the subject at the source end, and
   the absent-node assertion was answered by the separate first-seen query. Plants added at the far end: SECRET,
   another unit, another case. Removing `{predicate.where}` from the target branch is red on both adapters:
   `test_an_event_the_author_may_not_see_adds_nothing_and_is_never_a_first` (`(4, 100200.0) == (2, 200.0)`) and
   `test_frequency_counts_only_this_case_and_the_link_types_named` (`2 == 1`).
2. **An amount past Decimal128(9) was counted as a present 0.** The amount itself is now the decimal, so `count(amount)`
   counts only what is summed. `test_frequency_sums_amounts_as_decimals_and_skips_one_that_is_not` (1e30 and "inf" are
   no amount) is red on the earlier ClickHouse query: `(2, 0.0) == (2, None)`.
3. **The edge was pinned from one side only.** Every event is now 500 µs off every grid. A plant rounding the cut up to
   the millisecond turns both `[±1]` cases red (`1 == 2`).
4. **Ties were exercised by nothing.** `test_frequency_counts_events_at_one_instant_together` is red with a ROWS frame
   (`5 == 3`).
5. **`join_use_nulls`.** The query now sets `join_use_nulls = 0`. With it set to 1, seven cases are red (a `TypeError`
   on `int(None)`, or a count of 1 for 2).
6. **The two adapters summed differently** (exact decimal against DOUBLE). DuckDB now sums `DECIMAL(38, 9)` too, so 0.1
   and 0.2 make 0.3 on both. Red on DuckDB's old DOUBLE sum: `0.30000000000000004 == 0.3`. Spec 04 says it (rule 11).
7. **Records left uncommitted:** committed with this round.

- **Green:** the 13 frequency, access and case cases on c's ClickHouse.
- **The live delta at 778c4d8:** `gates/778c4d8.live.txt`, the analytics suite whole and every live file that
  evaluates rules.

### 12b. The orchestrator's independent review of L2.10 (at fea68fc)

1. **A sweep failure's counts, for a reader its rule's firings are hidden from (rule 7).** `rule_holds.readable_rule_audit`
   now withholds `rule_evaluation_failed` as it withholds `rule_evaluated`: no `findings`, no `documents_not_judged`,
   cardinality 0, and words without counts (`kyc_sweep.FAILED_WORDS_WITHOUT_COUNTS`, written beside the counted words).
   - The case: `test_a_routed_alerts_firing_is_withheld_from_the_rule_audit_outside_its_team`
     (`tests/ingest/test_typology_rules.py`, live). The entry is written by the sweep's own writer, `_say_unjudged`.
   - Red: on the live stack, with `rule_evaluation_failed` taken out of `_COUNTS_A_RULES_FINDINGS`
     (`gates/<head>.live.txt`).
2. **Re-gated at the head:** `gates/<head>.*`.
3. **`account_activity`'s decimal, introduced unreported by 778c4d8's edit.** DuckDB now matches it, both read through one
   `_decimal_amount`, with ADR-133 Amendment 10 and its four points. Overflow is refused, never wrapped, by
   `AmountTotalOutOfRange`.
   - Red on DuckDB offline: the activity case against DOUBLE (`(2, 0.30000000000000004) == (2, 0.3)`), and both signs of
     the overflow case with the refusal removed (2 failed). The ClickHouse reds are in the live record.
4. **The read-path purge through the real app.**
   `test_the_running_conduit_gives_the_alert_store_the_working_set_a_settle_purges_through`
   (`tests/ingest/test_typology_rule_routes.py`, live). Red with `app.py`'s `alerts_store.working_set = …` removed.
5. **The tie case:** four tied events, the unique largest span (`most_in_span == 4`). Red with a ROWS frame on c.
6. **Minors:**
   - approve_close's dataset refusal is `not_the_home_cases_author`, as dispose's is (`close_refusal`), and its case is red
     with the reason test removed (`assert 'own_change' == 'not_the_home_cases_author'`);
   - the team-leave case through a real signed token:
     `test_a_member_whose_token_no_longer_carries_the_team_reads_nothing_routed_to_it`, live;
   - `chooseByTyping` is one shared helper (`keyboard/chooseByTyping.ts`);
   - the records corrected (base 3be89a7; the lease intervals; the withdrawn fix's pointer).
