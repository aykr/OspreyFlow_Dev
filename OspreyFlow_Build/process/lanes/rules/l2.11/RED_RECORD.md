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

`tests/services/api/test_rule_drafts_store.py` needs Postgres, so it runs at the leased live run. Its plants
are listed there.
