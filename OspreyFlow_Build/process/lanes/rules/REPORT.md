# rules lane · report · rules-lists, second pass: the orchestrator's review and the owner's ruling on every close (12 November 2026, evening)

The review of 97826d0 found four rule-3 leaks and the owner ruled at about 15:30 that a close decides only the
citations its closer may read, for every disposition. All built in one pass; my lane-reviewer then found 15
defects, fixed below. Red first: `lists/AM7_RED_RECORD.txt` (offline P1 to P48 at their call sites, headed
by the commit and the code's identity) and `lists/REVIEW2_RED_BEFORE.txt` (the new cases against the code
before the pass). The live plants L8 to L23 (`lists/am7_live_plants.py`) are **not yet run**: they wait for
the orchestrator's word on a lease tonight. Am 7 rewritten as built.

| Review item | State | Proving test |
| --- | --- | --- |
| 1. Lists screened by clearance in the store's `WHERE`, for every caller; sentence words name no list | done | `test_screening_clearance.py` (equivalence with `handling_readable`, the KYC gate, a sentence rule, the preview, the words; P25 to P29); live `test_a_lists_entries_are_read_only_for_a_clearance_admitting_its_marking` (L8) |
| 2. A refresh's audit names and counts only cleared lists, shown only to cleared readers | done | `test_the_rule_audit_names_a_lists_re_screening_only_to_a_reader_cleared_for_the_list` (P30); the two marked refresh cases, live (L15) |
| 3. The Lists routes filtered, an access test each way; refresh, schedule and subscribe by a hidden name | done | live `test_a_list_is_shown_only_to_a_reader_cleared_for_its_marking`, `test_a_list_a_reader_is_not_cleared_for_is_answered_as_one_never_subscribed`, the store's case (L9 to L11, L14) |
| 4. The rule audit reads a cited firing as the queue does; Am 7's "Not changed" corrected; the test and P21 flipped | done | `test_the_rule_audit_reads_a_firing_citing_two_lists_as_the_queue_reads_its_alert` (P21) |
| The owner's ruling: a close decides only readable citations, every disposition, proposal and approval | done | `test_alert_citations_closing.py` (P31 to P35); live `test_a_close_decides_only_the_matches_its_closer_may_read`, `test_an_approval_by_a_reader_cleared_for_both_confirms_only_the_proposed_match` (L17, L18) |
| 6. Trends count a cited alert once per reader as the queue shows it | done | `test_the_trends_count_a_cited_alert_once_for_each_reader_as_the_queue_shows_it`; conformance `test_an_alert_kept_per_set_of_its_citations_is_counted_once_for_each_reader` (both adapters; P36 to P38, L19) |
| 7. A load's report counts only what its loader may read | done | `test_a_loads_report_counts_only_the_alerts_its_loader_may_read`, offline (P39) and live (L16) |
| 8. A reload never lowers a list's marking | done | `test_a_reload_that_would_lower_a_lists_marking_is_refused` (P40), live `…_is_refused_and_changes_nothing` (L13) |
| 9. The listed party keyed by its entry id | **done otherwise:** keyed by its name and every property it is written with, never failing past the bound; by entry id it needs an ontology version (not this lane's), logged | `test_a_match_reuses_its_own_entrys_party_never_another_entry_of_the_same_name`, `test_a_match_on_a_name_more_parties_share_than_the_lookup_reads_never_fails_the_rule`, `test_a_written_party_is_one_the_ontology_declares` (P24, P41, P42; live L23) |
| 10. Point 6 with a differing approver; Home's counts, Reports figures, the address; risk with a hidden factor | done | `test_an_approver_cleared_for_one_list_approves_only_that_lists_proposal`; `test_homes_counts_…`, `test_the_reports_figures_…`, `test_the_alerts_address_…`; live `test_a_reader_not_cleared_for_a_list_is_given_a_risk_its_hidden_match_takes_no_part_in` |
| 11. Out-of-map files listed for ratification | done | below |
| Notes: removal before close; the plants' code identity; collection error apart from red | done | the five fixtures; each record's header; the runners' BROKEN |
| Gates (`make test`, `make -k ci`, live) at the head | **waiting: the server's heavy slot, and nothing on the server from 12:00 UK on 13 November until the demo is over** | — |

**Out of the rules lane's map, for ratification (item 11).** `services/api/packs.py` (a pack item read by the
citations it shows); `services/api/screening_refresh.py` and `scripts/load_screening_list.py`, with
`scripts/seed_ledger_fixture.py` and `scripts/refresh_screening_list.py` (the store's new signatures);
`services/api/app.py` (the preview, *Test* and the four Lists routes); `services/api/rule_holds.py` (the rule
audit); `services/api/sentence_rules.py` and `rule_sentences.py` (a sentence's lists and words);
`packages/adapters/analytics_duckdb/{alert_facts,adapter,schema}.py`, `packages/adapters/analytics_clickhouse/{adapter,schema}.py`
and `packages/schemas/analytics.py` (`AlertFact.fact_id`, `hidden_from`); `spec/01_DOMAIN_MODEL.md`. Tests of
other areas changed for the new signatures: `test_rule_editor_routes.py`, `test_rule_sentence_routes.py` (the
scheme's dependency), `test_alert_evidence_withheld.py` (`TriageStore.triage_citations`, the real decision),
`test_alert_node_marking.py` (`save`'s `cited_handlings`), the analytics conformance suite (one case).

**The lane-reviewer's findings on the pass, and what became of each.** 1: `list_entry_id` was undeclared in the
ontology, so ArcadeDB would refuse every new party; the fakes accepted it (rule 15). Reworked as above, and
the fakes now validate writes and refuse a lookup on a field ArcadeDB cannot find by. 2: records claimed before
they existed; now recorded offline, and the live ones are said to be unrun. 3: self-approval beside another's
proposal, refused. 4: confirm read from the first proposal, now each its own. 5: a partial close cleared
another reader's claim, now kept. 6: a sentence alert on a hidden list shown to its subject's readers, now
marked as the list. 7: the hidden-name refusal is unique to hidden lists; the spec now says so, logged for the
owner. 8: the hold note, now only for the loader's own matches (held rows' reasons logged). 9: an unmarked list
is OFFICIAL for `hidden`. 10: the audit also reads the list's marking now. 11: item 7's call sites are planted
live only (L16, L20). 12: stored and served decider agree. 13: the positive route case added. 14: friction
row updated; the schemas commit is the orchestrator's to take, as before. 15: logged with 7.

## Decisions taken (second pass)
- A list's marking is kept apart from its entries (`screening_list_markings`), so an emptied list keeps it.
- A code change at the same classification counts as lowering (codes are not ranked): strict.
- A hidden list's name, offered for a new subscription, is refused before anything is written. That refusal is
  unique to hidden names, so it tells the administrator one exists (a name, not its contents). For the owner.
- The listed party is found by its properties, not an entry id: an entry id needs an ontology version.
- A close that leaves a citation open hands the alert back open and unassigned; a proposal leaves it claimed by
  its proposer. A claim and a suppression stay the alert's, shown to every reader (no list, match or count);
  a suppression's free-text reason is the lead's to word. Logged.
- Trends: one row per set of citations, at most six citations (else counted for no one, said in Am 7).
- A party written before entry ids is not found by id: a later match on its entry writes it once more.
- A list's refresh is recorded only for rules whose deployer is cleared for it.

# rules lane · report · rules-lists: CARRIES rows 113 and 114 (ADR-146 Amendment 7), 12 November 2026

Resumed from HANDOFF.md (stale: removed, never committed; no `wip(rules)` commit was on the branch).
Branch `lane/rules-lists`, rebased on main b4b570d, the packages/schemas commit at the head. Not pushed.

| Brief item | State | Proving test |
| --- | --- | --- |
| Row 113: every live file loading a screening list removes its own, in teardown (after the `yield`, so on failure too) | done: `test_kyc_rules`, `test_screening_refresh`, `test_screening_list_store`, `test_screening_list_routes` (`world`, shared by `test_list_refresh_schedule`), `test_list_refresh_schedule` (its lists renamed "Scheduled test ") | `test_kyc_rules.py::test_no_other_file_leaves_a_list_naming_this_files_people`, red before the teardowns (live plants L0, L0b), green after |
| Am 7, one owner on two lists: one alert citing both | done | `test_one_owner_on_two_lists_raises_one_alert_citing_both` (live, L1); `test_one_finding_cites_each_list_and_its_words_name_none` |
| Each list's citation and `owner_listed` shown only to a reader cleared for that list, at each read path (queue, explain, canvas, claim/release/dispose/approve/send back/assign, suppress, packs), each with a leak plant | done | `test_alert_citations_per_list.py` (28; plants P1–P10, P3b); live `test_a_reader_not_cleared_for_a_list_is_shown_the_alert_with_the_other_list_alone` (L3) |
| A list's marking (the rule-11 gap: lists carried none) | done: OFFICIAL/P by default; above the ceiling and unit-restricted codes refused; kept by an update and a refresh | `test_screening.py` (P11–P13, P22, P23); `test_an_update_keeps_a_marked_lists_marking` and the refresh's case (L5) |
| A true positive confirms only the matches the closer can read (the owner's ruling, 12:05) | done | `test_a_true_positive_confirms_only_the_matches_the_closer_can_read` (live, L2); `test_a_repoint_and_a_rename_rewrite_each_citation_with_the_alerts_own_lists` (L7, L2b) |
| What is written names no list (node sources, words, ALERTED_ON per list, trends, re-mark) | done | `test_alert_citations_written.py` (9; P15–P20, P24) |
| Point 8: a rule screens only lists its deployer is cleared for | done | `test_a_rule_screens_only_against_the_lists_its_deployer_is_cleared_for` (P14); live (L4, and the refresh L6) |
| Am 7 written as built, the rulings dated | done | `spec/06_DECISIONS.md` ADR-146 Amendment 7; reservation "written" |
| Offline gates (`make test`, `make -k ci`, schemas-check) | done, on the server's heavy slot (the orchestrator's go). At 962d6e0, domain-model-coverage-check was red on AlertCitation (mine, fixed in the domain model). At 086ed55, ci exit 0; make test 12921 passed, with two failures outside the branch | `gates/086ed55.{test,ci,triage}.txt`, `gates/962d6e0.*` |

Half-done: none.

**Records.** Offline plants at 8d1997e's tree: 25 of 25 red, the three files green built and restored
(`lists/AM7_RED_RECORD.txt`). Live plants on stack c at 0eae072: 10 of 10 red, built and restored green
(`lists/AM7_LIVE_RECORD.txt`). The broad leased run at 0eae072 (the live files the change reaches against main,
plus `test_route_rights.py`): 3419 passed, 36 failed, none of them in a file the change reaches. All 36 are triaged
in `gates/0eae072.live.triage.txt`: valkey on stack a's port, no model or stanza service, the apply harness, no
Azure blob settings, one case's residue that passes alone, and phase 8's exit, which fails at main the same way.
The rebase onto 5675103 overlaps rules-b only in the two spec files, so no code under the live run changed.
Stack c is down and released.

**Lane review.** 16 items; each fixed with its test and plant, or answered in Am 7 (see the friction row,
`process/friction/2026-11-12-rules-lists.md`).

## Decisions taken
- Point 8: a rule screens only lists its deployer is cleared for (the strict option; the orchestrator confirmed it stands).
- Three files keep their setup-time wipes of their own names: a killed run leaves nothing for the next run of that file to trip on.
- The rule audit stays strict: a firing that cites a hidden list is withheld whole.
- The trends undercount rather than leak: an alert is counted only for a reader cleared for every handling it rests on.
- A subscribed list takes its marking from its file, within the deployment's ceiling; a unit-restricted code is refused, since a list is read by every unit's rules.
- The approver of a two-person close is the closer the ruling means.

## Requests / carries
- Gates done (see the table). Branch rebased on main b4b570d. Main's later commits (to df2643b) are docs only and overlap no file of this branch.
- Carry: in the broad run, test_worker, test_ws_ticket and resolve/test_trigger reach valkey on 6379 rather than the leased stack's port. Phase 8's exit criterion fails on stack c at main.

# rules lane · report · rules-hyg, three hygiene carries, and the test_kyc_rules fix (10 November 2026, 20:30–23:30 UTC)

- **Item 1, Home's key cap: MET.** `.home-key` no longer dims itself; `homeKey.test.ts` reads the tokens and blends the key cap over the primary button's three faces in three themes: red on main (light 4.13, GOV.UK 3.91, and dark's pressed 3.59, which T3 cannot reach), green 9/9. T3's eight listings removed with it. Merger: no findings.
- **Item 2, the metrics panel's rarity note: MET, a harness artefact.** axe's `elmPartiallyObscuring`: the harness's 600px column let the panel spill 10.6px past BODY; it now scrolls as the product's side-panel slot does. axe measures the note in three themes; metrics scans 16/16, keyboard 8/8. Merger: no findings.
- **Item 3, schedule notices in *Needs you* (ADR-110 Amendment 19): MET after four review rounds.** Since L2.10 notices reached no screen. Owner alone in one statement (the orchestrator's ruling: no dataset reach); fixed sentences of eight kinds, and at read anything else becomes the fallback (rule 7); twenty with the total (rule 2). Plants red then green: route, words, Glass, and at the final head 6f4a6d4 all 10 live plants on stack b (`hyg/3-schedule-notices-red.txt`, round 4).
- **test_kyc_rules on main (off-step): isolation, fixed and merged (a8e9992).** A second screening list left in the shared Postgres by another live file; red 3/16 on stack c, green 16/16 on the same rows.
- **Gates at 13a04bc** (rebased on main 18d7870): see `gates/` (live, ci, test, every-harness, keyboard).
- **Round 5 at 16a4e76** (the merger's must-fix): an identity provider's refusal (`PrincipalExchangeRefused`: an account it no longer knows, an exchange refused, a token failing verification) is refused_rights and counts toward the three that pause again; only a fault that is no refusal is failed and uncounted. The executor's fake now raises only what the real resolver raises, and the fault case is the custom-role store's read failing (asyncpg). Am 19 names which outcomes pause. Live on stack b: the three files by name, 72 passed (`gates/16a4e76.live-named.txt`); 12 of 12 plants red then green (`hyg/3-schedule-notices-red.txt`, round 5). Code: 576fa06 and the schema at 16a4e76; this records commit sits above it, since the merger asked for no reorder after the gate.
- **Named live run at 6f4a6d4** (the merger's round 4; stack b under the rules lease, 2026-11-11T05:24Z, down and released): test_schedule_notices_needs_you 5, test_schedule_executor 51, test_schedule_notice 1, test_needs_you 14; 71 passed, none failed or skipped (`gates/6f4a6d4.live-named.txt`). Round 4 touched no Glass, so make test and every-harness stand at 13a04bc.

## Decisions taken
- Item 3 edits other lanes' files on the orchestrator's grants, by cross-session message (no commit holds them):
  Admin's (10 November ~21:20): `services/api/needs_you.py`, the `/v1/me/needs-you` route in `app.py` and
  `apps/workspace/src/admin/needsYou/**` (NeedsYou.tsx, needsYouApi.ts, NeedsYou.test.tsx), with "the keyboard case
  for the new row (keyboard.spec or needsYou's own spec)" (`keyboard/needs-you.spec.ts`) and "the axe looks in
  three themes"; `keyboard/needs-you-harness.tsx` (its `?notices=1` state) is not named and was taken as the axe
  looks' means: for the orchestrator to ratify. Studio's (~22:05): `services/api/scheduler.py`'s notice wording
  and `_Refused`'s kind, and `tests/services/api/test_schedule_executor.py`'s assertions; the new cases added to
  that file (the ArcadeDB, quota and exchange cases) go beyond "assertions": for ratification too.
  **Both ratified by the orchestrator (11 November, after ready-to-merge e5e3063):** the harness's `?notices=1`
  state (needs-you is under Admin's grant, and the harness serves its looks), and the new executor cases
  (`test_schedule_executor.py` is under Studio's grant). The merger lands the lane after the v0.5.0 tag.
- A packages/schemas change rides with the step in its own commit at the head (the orchestrator's standing instruction at a lane's start).
- Kinds beyond the ruling's five: still going and keyless refresh (already fixed words), and quota (new on main while the branch was open).
- The notice tip and the "more" line in plain words; the TS fields stay optional so a Glass reads an older Conduit as no notices.

## Requests / carries
- every-harness's `open=1&notices=1` and the new live file's Makefile and ci.yml lines: `hyg/hyg3_every_harness.diff`, `hyg/hyg3_ci_makefile.diff`, for the merger to apply.
- Carries: lane stacks are not fresh across `down`/`up` (admin's T1); one owner on two lists raises two alerts (ADR-146, tomorrow).
- Nothing of mine is running once the gates end; stack b released then.

# rules lane · report · UPG, the v0.4.12 → v0.5.0 upgrade rehearsed on ospreyflow-test (10 November 2026, 18:20–21:10 UTC)

- **Exit — rehearsed end to end, every step recorded: MET, with what stood in named.** Four runs (`gates/upg-rehearsal.txt`, `gates/upg-run1..4/`). Run 1 (main 5df2a3e): v0.4.12 → main, seven migrations; found update's files step breaks every pre-Amendment-2 deployment. Runs 2–3: platform-b's fixes failed (two-pass minting, undeclared volumes, gateway key; then reapply skipping `litellm-db`); a named update refreshing the wrong deployment found in code. Run 4 (platform-b d85f514, fresh v0.4.12): the refusal changes nothing (43/43 files), backup + apply bring it over (12 healthy, stores untouched, gateway key = Conduit key), files step a no-op, seven migrations, a v0.4.12 rule raises an alert after, 77 of 80 env keys byte-identical (every secret among them).
- **Exit — CHANGELOG's steps confirmed or corrected: MET for the migrations** (order; `migrate_rules_to_datasets` after `make_home_cases`; Rule author to assign; owners needing one) **and the refusal and first apply. NOT PROVEN** (owed to the orchestrator's post-tag check): `ospreyflow update` itself (no release; stood in by `harness.apply --build`, which moved the keys, so the second apply's move is unshown), today's update.py running its own files step, v0.4.12's rollback after the refusal, the lock's digests, `start` as recovery on d85f514, the `start --build` route, the default deployment (2480 held on that box).
- **Reviews:** the lane-reviewer found 13 anonymous volumes my teardowns left (runs 1, 2, 4) and the record calling them 0; overclaimed update steps; tail's exit statuses recorded as commands'; uncommitted helpers; unrecorded check failures. The orchestrator's review found the same claims plus REPORT replacing main's. All fixed; the 13 volumes removed by the owner (my session was refused). The teardown now fails on an orphaned anonymous volume, shown red (its first reds refused for the wrong reason, recorded).
- **Commits:** e08cb51, 45382f6, b1e65db, 407088d, 49f92d5, c773f12, c49e5d1, and the review fixes on top.

## Decisions taken
- Orchestrator's socket gone: took the one live slot, said so by heartbeat (confirmed right).
- Update cannot reach an unreleased head: v0.4.12 from its signed tag, the clone moved to each head's user-repo export, update's steps by hand; (a) emulated with v0.4.12's own rollback point (approved).
- Whole-deployment rule left pending (no second admin); provider key synthetic (`upg-synthetic-not-a-real-key-0000`); runs 2–4 without the prison pack.

## Requests / questions
- None open; carries are platform-b's (start --build on a release install; apply/stop on an unreadable compose file; the 2480 preflight). Nothing of mine is running; osprey-upg is gone from the server.

# rules lane · report · L2.11, the rule editor: declared dataset, draft, Test and Make live, the rule files, the migration (10 November 2026; resumed once; the review's must-fixes, gated at 0f319d4)

**What is done, half-done and untouched**

| Brief item | State | Proving test |
| --- | --- | --- |
| The declared dataset: chosen first, fixed once saved, only the case's own source or composite | done | `test_rule_editor.py::test_a_rule_is_declared_only_on_the_cases_own_source_or_composite`; `test_rule_editor_routes.py::test_a_rule_is_saved_only_on_the_cases_own_dataset_and_never_moved` |
| Conditions narrowed to the dataset's live model | done | `test_rule_editor.py::test_the_conditions_offer_no_type_outside_the_datasets_live_model`; the save, `test_a_save_naming_a_type_outside_the_datasets_live_model_is_refused` |
| Draft and live; Test over 30 days, its count the tester's alone (rule 7) | done | `test_rule_drafts_store.py`; `test_rule_editor_routes.py::test_a_rule_goes_live_only_once_tested_and_its_count_is_the_testers_alone` |
| Make live with the second person, from the dataset's `promotion_policy` | done | `test_rule_editor.py::test_a_composite_asks_for_a_second_person_when_any_member_does`; `test_rule_editor_routes.py::test_neither_the_author_nor_the_asker_sends_a_make_live_back`; `RuleEditor.test.tsx` (deploy_rules) |
| Changes: every step audited and listed | done | `test_rule_editor_routes.py`; `test_rule_maker_checker_routes.py` |
| Per-version .bpmn/.dmn via rules-b's `rule_files()`; Export with `stored=`; Show as BPMN | done | `test_rule_editor_routes.py` (codec equality); `test_rule_standards_routes.py`; `keyboard/alerts.spec.ts` (Escape) |
| The list picker (`list_id`) and `runs: list_refresh` that actually runs | done | `test_rule_editor.py::test_a_rule_reads_only_a_list_its_dataset_may_and_its_subjects_rows`; `test_rule_list_refresh.py` (9, the three call sites) |
| `migrate_rules_to_datasets`, dry run first | done | `test_migrate_rules_to_datasets.py` (7); `test_migrate_rules_to_datasets_store.py` (live) |
| The older routes kept for just_me only | done | `test_rule_sentence_routes.py` (409 `use_the_rule_editor`) |
| The Lists tab read-only (carry) | done | `ListsPanel.test.tsx`; `keyboard/alerts.spec.ts` |
| Keyboard (rule 13), axe, registry | done | `keyboard/alerts.spec.ts`, 8 ids in `registry-L2.11.patch`, each red with its handler removed; `a11y/every-harness.spec.ts` |
| Spec: ADR-146 Amendment 6, spec 03's six routes | done | — |
| ci.yml and Makefile wiring | half-done, by design | `L2.11_ci_yml.diff` for the orchestrator to apply; `test-file-coverage-check` green with it applied |

1. **Decisions taken under Prompt L, logged in MORNING.md** (PLAN.md has the reasons):
   - *Make live* reads the dataset's `promotion_policy`, and a composite asks for a second person when any member does.
   - Test runs over the stored draft, as its author, and goes no wider than the dataset's reach.
   - One draft and one live version per rule.
   - New rules can't take the whole-deployment scope; the migration converts the rules that already have it.
2. **Live, the rules lease, stack c, on the server:**
   - **The delta at 56e3c73** was `stack_lease.sh live rules` plus the lane's named files: 3305 passed and 38 failed. 36 of the failures were the server's, in files the diff doesn't touch (RED_RECORD §11 names them). Two were the lane's:
     - a send-back by a make-live's author or asker answered 409, not 403 `own_change`;
     - `test_schedule_notice` asserted behaviour main doesn't have.
   - **Both were fixed and shown red** at their call sites (`gates/5a1fb61.plants.txt`). The delta at 5a1fb61 passed 31, and each file passes alone too (`gates/5a1fb61.live.txt`).
   - Earlier deltas: `5fa7b83`, `953b7a1` and `6c80b31`. Stack c is down and released.
3. **Local, at 7ee2d56 / eae4092** (code identical; the latter adds records only):
   - **glass-keyboard**, with the registry patch: 747 passed and 4 failed. The four were in connections and ingest-studio and were caused by load; retaken alone, 55 of 55 passed. The eight new actions were each red with their handler removed.
   - **glass-a11y:** 963 passed.
   - **test-js:** 2970 of 2971. The miss was MatrixView's first-frame budget under load; it passed alone.
   - **`make -k ci`:** green apart from the Docker scans (trivy-image ×8, opentofu, chart) and `test-file-coverage-check`, which goes green with `L2.11_ci_yml.diff`.
4. **`make test` offline on the server:** 10,527 passed, with 12 failed and 13 errors, all expected (`gates/05ec309.test.txt`, at the head):
   - the three new live files (22 cases) run because their Makefile ignores are in the unapplied `L2.11_ci_yml.diff`, and `test_test_file_coverage_check` fails for the same reason;
   - the server's usual pair: valkey_config (main's own) and the webapp's GPU preflight.

   The first take, at eae4092, found a real defect, fixed at 05ec309 (RED_RECORD §13). The scheduled, folder-watched and command-line runs never had the rule's list reader or reach: `from_state` read them as state attributes no Conduit holds, and `RunResources` never built them. So on those paths a composite's rule read only the composite's own id, and a rule naming a list could not run. Both paths now build them from their own stores. The test is red with that building removed. Proven live at 291787c on stack b, at the orchestrator's ask: 278 passed, none failed (`gates/291787c.runpath.live.txt`).
5. **Reviews:**
   - My lane-reviewer's 29 findings were all built, with plants (RED_RECORD §10).
   - The orchestrator's conditions were met: list_refresh runs, the ci wiring is a diff, registries are passed by their literal names, test_schedule_notice is repointed, and Make live is gated on deploy_rules.
   - rules-b's L2.11a codec is integrated (RED_RECORD §8).
6. **The orchestrator's independent review at 291787c: four must-fixes, built** (RED_RECORD §14; Amendment 6 point 11, decisions 12 and 13). Each is red by a plant at its call site.
   1. **Rule 3.** A scheduled or refreshed rule now reads its declared dataset alone, never the author's whole case scope (the layer included). Once its case stops reading that dataset, it is refused in words.
   2. **`POST …/rules`.** It keeps a pattern or template rule just for its author: the author's own alerts, no `Alert` node. A case-wide one is refused, 409 `use_the_rule_editor`. The form says so, and its five keyboard cases end at a just-for-me rule.
   3. **Who a rule runs as.** On a load, a slot and a refresh, the author must hold `author_rules` or `deploy_rules`. So a Rule author's scheduled rule runs.
   4. **Rule 12.** Whoever asked for a make-live can't approve it; this is now tested.
   - **Re-gated:**
     - offline: the rule files pass, and the five offline plants are red;
     - live, at 5b4c6ba on a fresh stack b: 666 passed, and the two live plants are red. The three KYC failures are an existing order dependence; they fail alike without this change;
     - `make -k ci` and `make test`: make -k ci on the server at 0f319d4 (`gates/0f319d4.ci-server.txt`) is green apart from `test-file-coverage-check`, which waits on `L2.11_ci_yml.diff`. The eight trivy image scans, opentofu and chart ran for real and passed. make test on the server at 877971a (`gates/877971a.test.txt`): 10,531 passed, with 15 failed and 13 errors:
       - the new live files the unapplied diff leaves in, and the coverage test;
       - valkey_config and the GPU preflight;
       - two `test_alerts_and_the_layer` cases, the same fixture gap as decision 13's others. Fixed at 0f319d4; the file passes, 12 of 12.
7. **Ratification list:** files this step changed outside the rules lane's own (`apps/workspace/src/alerts/**`, and the alerts, rules, watches and monitoring modules and routes):
   - Ratified earlier: `scripts/migrate_rules_to_datasets.py`, `services/api/audit_section.py`'s actions, the Studio list routes' refresh hooks in `app.py`, `recipe_run.py`'s fields, and the schemas (`sentences.py`, `domain.py`, `monitoring.py`, the new `rule_editor.py`, `generate_ts.py` and `generated/`).
   - New since: `run_resources.py`'s `rule_lists` and `rule_reach` (§13); `domain.py`'s `TypologyRuleInput.just_me` (decision 12); the keyboard harnesses and `a11y/every-harness.spec.ts`.
   - Ingest's test fixtures, given a role so that their rules run (decision 13): `tests/ingest/{test_typology_rules,test_kyc_rules,test_rule_writes_in_the_record,test_typology_rule_routes}.py`.
   - `tests/services/api/{test_schedule_notice,test_load_records,test_recipe_run_path,test_run_resources}.py`.
8. **Carries for tomorrow** (the orchestrator's no-new-scope note):
   - **The template-to-draft path.** The editor's draft, *Test* and *Make live* for a pattern or template rule (decision 12's open point). *Test* previews sentences only.
   - **The composite list ambiguity** (the review's item 5).
   - **`test_kyc_rules.py`'s order dependence.** Three cases read the screening matches that earlier cases left in the shared ArcadeDB graph. Seen on main's gates too.
   - **Does a scheduled run's notice still reach a screen after L2.10?** The one queue gives a notice no kind (`alerts._KIND_SQL`), so it sits only in its owner's own list (`AlertStore.list_authorized`). Whether the Glass still shows that list is unverified. It loses a notice; it is not an access problem.
   - **Main's test-file `ruff` drift**, seen while fixing: `test_rule_editor_routes.py` and several app.py `# fmt: skip` blocks don't pass `ruff format --check` run from Core. They pass the project's own lint.

---

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

**The orchestrator's independent review at fea68fc: sent back, and built** (RED_RECORD §12b):
1. **Rule 7.** A sweep failure's counts are withheld from a reader its rule's firings are hidden from, as `rule_evaluated`'s are. Red on c with the withholding removed.
2. **Re-gated at 1e94fdf:**
   - `make -k ci` here: green apart from the image, opentofu and chart scans (Docker off);
   - `make test` on the server: 9,531 passed, and 2 failed, both the host's (valkey_config, which is main's, and the GPU preflight);
   - test-js: 2,762 of 2,763, the miss the MatrixView timing case.
3. **`account_activity`.** It reads amounts as decimals on both adapters through one `_decimal_amount`, under ADR-133 Amendment 10:
   - each amount is rounded to 9 places;
   - one past 10^29, inf or nan is no amount;
   - a total of 10^28 or more is refused (`AmountTotalOutOfRange`), never wrapped. DuckDB's plain decimal SUM was found to wrap silently.
4. **The read-path purge** is proved through the real app. Red on c with the lifespan's line removed.
5. **Ratification list** updated (item 12).
6. **The tie case** is four tied events. Red on c with a ROWS frame (`6 == 4`).
- **Minors:**
  - approve_close's dataset refusal is `not_the_home_cases_author`;
  - the team-leave case runs through a real signed token;
  - one `chooseByTyping`;
  - one friction row;
  - the records' base, lease intervals and withdrawn-fix pointer corrected.
- **Live, the rules lease on stack c:**
  - The five plants were each red for their own reason. The delta at 1e94fdf passed 317, with 9 failures: a defect of that commit's own, a NULL activity sum read by `float()`.
  - Fixed at bb4466d. Its delta, the analytics suite whole, passed 266 (`gates/1e94fdf.live.txt`, `gates/bb4466d.live.txt`).
  - Released and down.

**The orchestrator's re-review at 724d297: sent back, and built at d52fc9f** (RED_RECORD §12c):
1. **A sweep failure's documents not judged** are counted across every customer the rule screens, so the count and its counted words are withheld from every reader of the rule audit; the words without the number are kept. Red on c by two plants (the count withheld only when a firing is hidden; a digit kept in the words).
2. **`account_activity`'s own refusal, shown alone:** a total of 1.2 × 10^28 that the decimal holds but the limit refuses. Red with only that call removed, on DuckDB offline and ClickHouse on c.
3. **Minors:** ClickHouse's activity comment; ADR-133 Amendment 10 point 3 narrowed; a team member leaves from their next token (ADR-146 Amendment 4 point 1, `alert_routing.py`); ruff and mypy on the files changed since `make -k ci` (`gates/d52fc9f.lint.txt`).
- **Live, the rules lease on stack c:** the three plants red; the delta at d52fc9f passed 289, none failed (`gates/d52fc9f.live.txt`). Released and down.
- **`glass-keyboard` at 6e90f52** (`registry-L2.10.patch` applied uncommitted, then reverted; the orchestrator's local slot): 689 passed, 1 skipped, 2 failed, both main's own (`boards.spec.ts:225` and `:423`, fixed in f6def92 on lane/case) (`gates/6e90f52.keyboard.txt`).

**Rebased onto today's main and re-gated (the orchestrator's ask, 10 November)** at b40bd93, base main at 6379dd1:
- **The rebase:** onto 380987e, then again onto 6379dd1, since P5b landed during the first. Five conflicts, each resolved by keeping both sides: app.py's imports, test_place_routes.py (Admin › Audit's row and L2.10's watches and teams rows), the decision log and citation allowlist (both appended), and ADR_RESERVATIONS.md (one row each for ADR-146 Amendment 4 and ADR-133 Amendment 10, both written: the duplicate fixed).
- **`make test` on the server** at c9c1061 (`gates/c9c1061.test.txt`): 10,200 passed, 12 skipped, 4 failed; test-js 2,900 of 2,901 (the MatrixView first-frame budget under load).
  - Two failures are the host's: test_valkey_config (main's own) and the GPU preflight.
  - Two were L2.10 meeting today's main, fixed at b40bd93: five L2.10 audit actions unclassified in main's new audit kinds (added to `audit_section.py` with the other alert actions, ratified by the orchestrator), and the Reports Viewer journey naming the two inbox routes L2.10 removed. Both files pass again (16 passed). The orchestrator ruled that the narrow fix needs no full rerun.
- **Live, the rules lease on stack c** at b40bd93, 09:17–10:27Z (`gates/b40bd93.live.txt`): test_route_rights and the 48 live files, 801 passed, none failed. Down and released.
- **`make -k ci`** at b40bd93 (`gates/b40bd93.ci.txt`): green apart from the eight `trivy-image-*` scans, opentofu-check and chart-check, which need Docker (off on this Mac).
- **`glass-keyboard`** at b40bd93 (`registry-L2.10.patch` applied uncommitted, then reverted; `gates/b40bd93.keyboard.txt`): 731 passed, 1 skipped, none failed. Main's two board failures are gone at this base.
- **Main moved again** during the re-gate (to 17c202d, 144 commits). Not rebased again, since the lane is gated.

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
    - the live and server records: 3b6ed0e, then the deltas at 274d114 and 778c4d8;
    - the orchestrator's review: 77c5a56 api, 12d5488 analytics, 86366d7 workspace, 1e94fdf records, bb4466d the live run's fix, then the gates and this report;
    - the re-review: d52fc9f the fixes, 6e90f52 its live records, then the keyboard record and this report;
    - the rebase onto 6379dd1: b40bd93, L2.10 meeting today's main; then the re-gate's records.
    - then this report and the friction row.
15. **Still running:** nothing. The lease on c is released, its stack is down, and no server run is alive.
