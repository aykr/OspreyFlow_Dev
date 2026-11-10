# L2.11 · red record

Each new test is shown red by a fault planted at the real call site, then green with the plant removed
(process/CLAUDE.md rule 15). Offline runs are on this Mac, on the closed ports, with OSPREY_LANE unset. Live
runs name their lease and stack.

## §1 The declared dataset, its model and its second person (`services/api/rule_editor.py`), offline

`tests/services/api/test_rule_editor.py`: 4 passed, then one plant at a time.
1. **The whole ontology offered** (`ontology_in` ignores the packs): red, only
   `test_the_conditions_offer_no_type_outside_the_datasets_live_model`.
2. **Any chosen dataset declared** (`declared_dataset` ignores the kind, so a drawn dataset passes): red, only
   `test_a_rule_is_declared_only_on_the_cases_own_source_or_composite`.
3. **A composite's own policy only** (`needs_second_person` reads no members): red, only
   `test_a_composite_asks_for_a_second_person_when_any_member_does`.

## §2 The store's draft, Test and Make live (`services/api/typology_rules.py`), live

Live: the rules lease, stack c, by `stack_lease.sh remote`, at 5fa7b83 (`gates/5fa7b83.live.txt`).
- **First:** the new store and route files, with the rule tests they touch (route rights, maker-checker's
  store and routes, the schedule, the sentence store): 50 passed.
- **A test that passed on another file's state.** Run alone, `test_rule_editor_routes.py`'s *Test* cases
  failed unplanted. The route returned 500, because the test gave no screening-list store. The combined run
  had passed only because an earlier file had left one on `app.state`. The test now gives one (5 passed
  alone), and the first round of plants is recorded as void for that file.
- **Each plant again** (a whole planted file swapped in at its real call site, then restored). Red only
  where it should be:
  1. A new rule saved live: the draft and never-runs cases, store and route, and those built on a draft.
  2. The dataset check removed: only the two dataset-fixed cases.
  3. Made live untested: only the two untested cases.
  4. A test kept on a draft saved again: only `test_a_test_of_a_draft_saved_again_meanwhile_is_refused`.
  5. The author approving their own: the two second-person cases, and maker-checker's own-approval cases.
  6. A sent-back make-live retired: only `test_a_make_live_sent_back_returns_to_its_draft`.
  7. Test's count told to everyone (rule 7): only the tester-alone route case.
  8. The second-person policy ignored: only the second-person route case.
  9. An editor's approval asks for the administrator: only the second-person route case.
- Released and down.

## §3 The migration (`scripts/migrate_rules_to_datasets.py`), offline

`tests/test_migrate_rules_to_datasets.py`: 5 passed, then one plant at a time.
1. **The dry run handed the real writer:** red, only `test_a_dry_run_writes_nothing`.
2. **A rule converted with a dataset that has no home case left out:** red, only
   `test_a_dataset_with_no_home_case_leaves_the_rule_whole_and_running`.
3. **The copies left whole-deployment:** red, only
   `test_one_rule_per_dataset_in_its_home_case_with_the_same_conditions_and_the_original_retired`.
4. **A rule never approved copied live:** red, only `test_a_rule_never_approved_is_copied_as_a_draft`.

The store case (`test_migrate_rules_to_datasets_store.py`, its own schema, seeded as a store before L2.11)
ran live on stack c (the rules lease) at 953b7a1 (`gates/953b7a1.live.txt`). With the store and route files and
the rule tests they touch, 52 passed. It proves:
- the dry run at `_main` changes no table, column, index or row;
- the real run leaves no whole-deployment rule, and one rule per dataset with the same conditions;
- a second run changes nothing.

Red with the bootstrapping store opened on a dry run: only
`test_the_dry_run_at_its_real_call_site_changes_no_table_column_index_or_row`. Released and down.

## §4 The team's member count for "where its alerts go" (`read_alert_teams`), offline

`test_the_teams_a_rule_may_go_to_list_members_to_the_lead_alone` now also asserts the deployer is told how many
of each team hold the case (2 and 1), with no one named. Red with the count taken from the lead-only list
(`member_count=len(members)`): 1 failed.

## §5 The Glass editor (`alerts/RuleEditor.tsx`, the builder's editor mode), offline

`alerts/RuleEditor.test.tsx`: 6 passed, then one plant at a time, red only in its own case.
1. **The deployment's ontology offered** (the builder reads `/v1/ontology` in editor mode): red,
   "offers the conditions from the dataset's live model, never another dataset's or the deployment's".
2. ***Make live* before a test** (enabled on `busy` alone): red, "saves a draft on its dataset, and makes it live
   only once tested".
3. **The team named without its count:** red, "says where its alerts go before saving, with how many of the
   team hold the case".

## §6 The Lists tab read-only (carry, ADR-133 Amendment 9), offline

`alerts/ListsPanel.test.tsx`: 6 passed. Red with a *Refresh now* button put back for whoever may load lists: only
"offers no add, refresh or schedule even to whoever may load lists, and shows their refreshes". The keyboard case
is replaced by the read-only one. The registry patch drops `refresh-a-screening-list-by-keyboard`,
`subscribe-to-a-screening-list-by-keyboard` and `set-a-list-refresh-schedule-by-keyboard`. The Conduit's routes
stay for the operator's command until the tab is retired.

## §7 The list picker (carry 11): a rule names one Studio list its dataset may read, offline

`test_a_rule_reads_only_a_list_its_dataset_may_and_its_subjects_rows` (`rule_editor.list_entries`): 5 passed in
`test_rule_editor.py`, then one plant at a time.
1. **Every dataset's lists searched,** not the rule's own (another dataset's list read, rule 3): red, only that case.
2. **Rows of every type read** (the subject's type filter removed): red, only that case.

Glass: `RuleEditor.test.tsx`'s "offers the screening lists the dataset may read, and saves the one chosen" (7
passed). StageD's case for the retired schedule form is removed with the form.

## §8 On L2.11a (rebased onto main at cf48b21): the real codec, the stored files served, Show as BPMN

- **Export at the route** (`test_the_export_route_serves_the_files_stored_beside_the_rules_version`, offline):
  18 passed in `test_rule_standards_routes.py`. Red with the route rendering afresh instead of serving what was
  stored: only that case.
- ***Show as BPMN* mounted on the draft** (`RuleEditor.test.tsx`): 8 passed. Red with the dialog not mounted:
  only "shows the saved draft as BPMN, drawn from the files saved beside it".
- **The stored files are the real codec's at every saved version**
  (`test_the_stored_files_are_the_codecs_at_every_saved_version`). Live on stack c (the rules lease) at 6c80b31,
  with the store, route and migration cases and the rule tests they touch: 53 passed (`gates/6c80b31.live.txt`).
  Red with the draft's files not rewritten on a second save: that case and the store's
  `test_saving_again_replaces_the_one_draft`, nothing else. Released and down.

## §9 *When* a screening list refreshes, offline (the orchestrator's condition: no rule saved to run on a refresh that never runs)

`tests/services/api/test_rule_list_refresh.py`: 3 passed, then one plant at a time.
1. **A refresh starts no rule** (`on_list_refreshed` returns at once): red, the runs-each-rule case, and the
   refused-author case, which records nothing either.
2. **Every outcome starts the rules** (the hook's `updated` check removed): red, only "a refresh that kept nothing
   new starts no rule".
3. **A refused author run anyway:** red, only "a rule whose author cannot act is recorded refused, never run".

The store's `test_a_list_refresh_reads_only_the_running_rules_that_name_that_list` runs at the next leased run.

## §10 The lane-reviewer's L2.11 round (items 1 to 29), offline

All offline (480 passed across the rule suites at 17fc646). The live cases run at the next leased run.
- **List refresh at its three call sites and in its own judge** (`test_rule_list_refresh.py`, 9 passed): each plant
  is red only in its own case. The plants:
  1. *Refresh now*'s hook removed;
  2. the scheduled refresh's hook removed;
  3. the dataset's own import's hook removed;
  4. a refresh judged as a schedule ("no schedule");
  5. the list's owner not asked (another dataset's same-id list);
  6. no stop after three refusals.
- **The migration** (`test_migrate_rules_to_datasets.py`, 7 passed): the copies' own patterns, a rule changed while
  it runs left for the next, and a rule whose pattern cannot be read left whole.
- **The older routes** (`test_rule_sentence_routes.py`, 9 passed): only a rule just for its author.
- **The Glass:** `RuleEditor.test.tsx` 9 passed, the opened rule included, and `SentenceBuilder.test.tsx` updated;
  113 passed across `alerts/`.
- **Keyboard:** four new cases plus the moved team case, registry ids in the patch (+8, −3 in all). Shown red with
  each handler removed at the local keyboard gate.
- **Axe:** two editor states, `tab=rules&editor=tested` and `tab=rules&editor=bpmn`, scanned at the local axe gate.

- **Make live offered only with `deploy_rules`** (the orchestrator's minor, after the review): `RuleEditor.test.tsx` 10 passed; red with the gate opened (Make live shown to a Rule author): only that case.
