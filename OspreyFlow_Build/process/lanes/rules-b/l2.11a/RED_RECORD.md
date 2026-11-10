# rules-b · L2.11a · red record

Each plant was made in the code under test, at the call site the import route uses (`from_files` over
bytes `to_bpmn`/`to_dmn` really wrote, with one element or attribute added), run, and then restored
(`diff` clean). The runs were offline on closed ports, with no lease.

## §1 The codec (`packages/rule_standards/codec.py`; `tests/rule_standards/test_codec.py`, 33 cases)

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
