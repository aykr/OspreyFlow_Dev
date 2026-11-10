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
