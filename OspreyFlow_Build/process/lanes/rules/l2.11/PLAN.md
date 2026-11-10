# L2.11 · the rule editor (rules' part) · plan

Started 10 November 2026 from main at fb704c4, after L2.10's merge (ab42128). Binds: ADR-146 decision 3 and its
tests (`06_DECISIONS.md` "Tests that would fail"), ADR-146 Amendment 5 (rules-b's codec, L2.11a), ADR-145 A3 and
decision 8, ADR-140 R12 (draft and live), process/CLAUDE.md rules 3, 4, 7, 8, 12, 13 and 15.

Split (the orchestrator, 10 November): rules-b builds the BPMN 2.0/DMN codec, Export, the import refusal and the
read-only *Show as BPMN* dialog. Rules builds the rest and mounts the dialog. The contract is in the memory
note l2-11-rule-files-contract: `rule_standards.rule_files(rule, dataset_id=…)` at every saved version, and
`export_rule_file(…, stored=…)`.

## What exists (survey, 10 November)

- **One store for every rule:** `TypologyRuleStore` (`typology_rules.py`).
  - Tables: `typology_rules`, plus `typology_rule_versions` (a version per save).
  - Status is `pending|active|retired`. `pending` is maker-checker for whole-deployment rules only. There is no draft.
  - `dataset_id` is set implicitly from `made_in(principal)` on create and again on every change.
- **Routes** are case-scoped, under `/v1/investigations/{id}/rules…`.
  - Writes need DEPLOY_RULES. `author_rules` is read nowhere.
  - The preview runs over 90 days on an unsaved sentence.
- **The Glass `SentenceBuilder`:** the deployment ontology, no dataset choice, no draft, Test or Make live, no
  "where its alerts go" sentence with a count, and no list-refresh trigger.
- **The pattern to copy:** a dataset's live model as types (`boards.dataset_node_types` and
  `dataset_link_types`); the R12 draft/live shape (`target_models.py`); a dry-run migration
  (`scripts/migrate_cases_to_one_dataset.py`).

## Decisions taken (Prompt L; for the owner to overrule, logged in MORNING.md)

1. ***Make live*'s second person reads the dataset's existing policy** (ADR-145 A3/decision 8, `promotion_policy`):
   - `second_person_reviews` means a rule goes live only on another person's approval. They hold deploy_rules
     at the case's Author level, and the author can never approve their own.
   - `author_promotes` means the author makes it live.
   - A composite has no policy of its own, so it asks for a second person when any member dataset does.
   - *Why:* ADR-146 names A3, the only per-dataset policy built. A separate "making rules live" setting would
     need Admin's row and file. If the owner wants the two apart, it is one column and one Admin control later.
2. ***Test* runs over the last 30 days**, as ADR-146 says. It runs on the stored draft version, as its author,
   over the declared dataset.
   - The result (would_raise and the version tested) is kept on the version.
   - *Make live* is refused unless the draft being made live is the version tested.
   - The old 90-day preview of an unsaved sentence stays as the builder's live preview until the editor
     replaces it.
3. **Draft and live, as R12:**
   - A rule has at most one draft version and one live version.
   - *Save* writes a draft version, with its `.bpmn` and `.dmn` from `rule_files()` in the same transaction.
     It needs author_rules at the case's Author level.
   - *Make live* needs deploy_rules.
   - Every step is audited and listed in *Changes*: `rule_draft_saved`, `rule_tested`, `rule_made_live`, and
     `rule_make_live_proposed`, `_approved` and `_sent_back`.
4. **The declared dataset:**
   - Chosen on create, from `datasets.chosen_of_case` (the case's source or composite). Anything else is
     refused as missing (404 `dataset_not_found`).
   - A change naming another dataset is refused (409 `rule_dataset_fixed`).
   - The conditions are checked against that dataset's live model types, properties and links, and its
     offered lists. A type outside it is refused.
5. **When:** adds "when a screening list refreshes" (`runs: list_refresh`).
   **Then:** a severity, to a named team or to the dataset's home case.
   - New rules can no longer take the whole-deployment scope (`deployment`); the migration converts the ones
     that exist.
6. **`scripts.migrate_rules_to_datasets`:**
   - It writes, for each whole-deployment rule, one rule per dataset the deployment loads, in that dataset's
     home case, with the same conditions, and retires the original.
   - It runs a dry run first, which writes nothing; the copy follows `migrate_cases_to_one_dataset`'s DryRun.
   - A dataset with no home case is reported, not guessed.

## Steps (each a commit with its tests first, each red by a plant at its real call site)

1. Schema: `SentenceRuleInput.dataset_id`, `runs: list_refresh`, `RuleState` and the version fields. Tell
   rules-b and case before committing.
2. Store: versions gain state, tested and files; draft, test, make live, approve and send back; the dataset fixed.
3. Routes: save draft, test, make live, approve and send back, read the stored files; `test_route_rights` rows.
4. The dataset's offered model and lists for the editor (the rules place's rights, rule 3).
5. Migration script, dry run first.
6. Glass: the dataset choice first, the form, "where its alerts go" with a count, Test, Make live, Changes, and
   *Show as BPMN* mounted; keyboard cases and the registry patch; axe in three themes.
7. Carries: the list picker on `/reference-lists/offered`; the Lists tab read-only.
8. Spec: ADR-146 Amendment 6 (reserved), spec 03 and 02; then the gates and the report.
