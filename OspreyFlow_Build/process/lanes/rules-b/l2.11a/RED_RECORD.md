# rules-b · L2.11a · red record

Each plant was made in the code under test, at the call site the import route uses (`from_files` over
bytes `to_bpmn`/`to_dmn` really wrote, with one element or attribute added), run, and then restored
(`diff` clean). The runs were offline on closed ports, with no lease.

## §1 The codec (`packages/rule_standards/codec.py`; `tests/rule_standards/test_codec.py`, 33 cases at first; 48 collected after §5, 46 run and 2 skipped by schema)

| Plant | Red |
| --- | --- |
| `from_files` never raises `UnsupportedElements` | the BPMN gateway, the DMN element, the `osprey:` element and attribute, and another vendor's attribute (4) |
| attributes not checked | the `osprey:` attribute and the vendor's attribute (2) |
| any `osprey:` element let through | `test_an_unknown_osprey_element_or_attribute_is_refused_by_name` |
| `scope` not written on `osprey:raise` | round trip of *on a hotlist* (just me) and *the whole deployment* |
| any DMN cell read as an equals word | `test_a_dmn_cell_outside_the_forms_written_is_refused` |
| a missing dataset accepted | `test_a_rule_file_naming_no_dataset_is_refused_in_words` |
| sequence flows not checked | `test_the_process_must_be_the_three_elements_in_order` |
| the two files' names not compared | `test_the_two_files_must_be_of_one_rule` |

## §2 The routes (`services/api/rule_standards_routes.py`, the three routes in `app.py`; `tests/services/api/test_rule_standards_routes.py`, 10 cases)

The fake store refuses what the real `get_listed` refuses (another case's rule; a rule in a dataset the
reader's case does not read). The real store's refusal is the live file's (§3).

| Plant | Red |
| --- | --- |
| import's dataset not checked | `test_a_dataset_outside_the_case_is_refused_as_a_missing_one` |
| no upload cap | `test_a_file_over_the_cap_is_refused_before_it_is_read` |
| the model not checked (`check_sentence` gone) | `test_an_imported_rule_naming_an_undeclared_property_is_refused_in_words` |
| import under `deploy_rules` | `test_import_needs_author_rules_and_the_author_level` |
| import at the Viewer level | `test_import_needs_author_rules_and_the_author_level` |
| export without `require_rules_place` | `test_export_needs_the_right_the_place_and_the_case` |
| export reading any case's rule | `test_a_rule_the_reader_may_not_see_is_the_same_404_as_a_missing_one` |

A first attempt at a "parsed before the cap" plant was a no-op (`… if False else None`). It passed, as it
should have, and proves nothing, so it is not counted. The "no cap" plant is the one that counts.

## §3 The live file (`tests/ingest/test_rule_standards_routes_live.py`)

Lease rules-b on stack d (server, remote), 10 November 2026. Two runs: `gates/e81e8a2.live.txt` (08:51–08:55Z)
and `gates/e81e8a2.live-2.txt` (08:56–08:59Z).
- **The set** (the live file, `test_route_rights.py`, `tests/ingest/test_typology_rule_routes.py`,
  `test_rule_maker_checker_routes.py`, `test_rule_schedule.py`, `test_audit_section_store.py`, and the
  offline route and level tables): 301 passed, 1 failed. The failure was
  `test_every_right_guards_at_least_one_route`: `author_rules` is now guarded (the import), so it came off
  the table's not-yet list. That is the table working. On the re-run, `test_route_rights.py` passed (4).
- **The first reach plant was malformed and is not counted.** It dropped `{reach}` but left its argument,
  so asyncpg refused the query's argument count. It was red for the wrong reason (rule 15).
- **The second reach plant** dropped both the clause and its argument in `get_listed`, on the server's copy
  only, and was restored (`cmp`). `test_export_reads_through_the_real_rules_lists_reach` went red: the
  hidden rule's DMN was served with a 200.
- The live file has changed since (§5: a JSON body, the declared dataset returned, the case's layer, a
  real dataset read by another case), so it needs a second leased run (§6, at the gates).

## §4 *Show as BPMN* (`src/alerts/ruleStandards/`; `ShowAsBpmn.test.tsx`, 5 cases)

The drawing is tested against `fixtures/visits-to-listed-people.bpmn`, which
`test_the_workspace_fixture_is_the_codecs_own_output` keeps equal to `to_bpmn`'s output.

| Plant | Red |
| --- | --- |
| focus not given back to the button | `gives focus back to the button when it closes, by Escape or by Close` |
| Escape not handled | the same case |
| the sequence flows not checked (the whole condition removed) | `does not draw a process OspreyFlow does not run` |
| a second end event drawn as the first | that case, and `says so, and draws nothing, for a file that is not a rule's process` |

A first flows plant removed only `flows.size !== 2`, so the other two checks still caught the crossed
flow. It passed, and is not counted.

The keyboard spec's reds (each id's handler removed) are recorded with the Playwright run.

## §5 The lane-reviewer's round (findings 2, 3, 5, 6, 9, 10, 11, 13 and 15; each red by a plant, then restored)

| Plant | Red |
| --- | --- |
| every kind in the case declarable (the source/composite check gone) | the layer, borrowed-layer and drawn cases (3) |
| the declared dataset not returned | `test_an_exported_rule_imports_back_to_the_same_rule` |
| no streamed body cap | `test_a_body_over_the_cap_is_refused_as_it_streams` |
| no declared-length check | `test_a_declared_length_over_the_cap_is_refused_before_the_body_is_read` (see note) |
| `forbid_dtd=False` | `test_a_bare_document_type_declaration_is_refused` |
| tab and line breaks not escaped | `test_a_name_with_a_tab_or_a_line_break_comes_back_the_same` |
| numbers written by `repr` | the `1e-05` and `1.5e+20` cases |
| places not checked | `test_an_element_out_of_its_place_is_refused_by_name` |
| an attribute the model drops let through | `test_an_attribute_the_rule_would_drop_is_refused_by_name`, `test_a_team_is_refused_while_the_sentence_cannot_name_one` |
| a second output let through | `test_a_second_output_is_refused` |
| `dateTime` for the time column's type | `test_a_time_column_is_typed_as_dmn_names_it` |
| Escape not kept from the editor (`stopImmediatePropagation` gone) | `takes Escape for itself, so the editor around it does not act on it too` |

Note on the declared-length check: its first test also streamed the body, so the streamed cap caught it
and the plant stayed green, which is rule 15's fallthrough. The case that counts now makes reading the
body itself an error.
