# admin · T1 part 3 red record (10 November 2026)

Each check was planted out at its real call site, its test run red, and the file put back and green. These plants were
run by hand, one at a time. Offline: closed ports, no lane.

| Plant | File | Test | Red |
| --- | --- | --- | --- |
| No `live_select.py` (the tests written first) | `OspreyFlow_Build/tools/live_select.py` | `test_live_select.py` | collection error |
| No route-rights floor | the same | `…graph_adapter_selects…`, `…empty_change_still_selects_route_rights`, `…rule_names_none_all_or_tests` | 3 failed |
| An unmapped path selects nothing | the same | `…path_no_rule_covers_selects_the_full_set`, `…removed_python_file_selects_the_full_set` | 2 failed |
| Imports inside functions not followed (`tree.body` for `ast.walk`) | the same | `…import_inside_a_function_and_a_module_named_in_a_string…` | 1 failed |
| Modules named in a string not followed | the same | the same | 1 failed |
| Conftest files not followed | the same | `…conftest_s_imports_count_for_every_test_beneath_it` | 1 failed |
| No `live` verb (the tests written first) | `OspreyFlow_Build/scripts/stack_lease.sh` | `test_stack_lease.py -k live_` | 3 failed |
| An empty selection not refused | the same | `…live_refuses_an_empty_selection…` | 1 failed |

| **After my lane-reviewer's pass**, 18 cases in `test_live_select.py`: | | | |
| Renames detected (`--no-renames` dropped), so a renamed module's old path is never seen | `OspreyFlow_Build/tools/live_select.py` | `…rename_is_its_old_path_and_its_new_one…` (a real git repository) | 1 failed |
| Adding rules ignored | the same | `…adding_rule_adds_to_what_imports_reach` | 1 failed |
| A rule naming no live file accepted | the same | `…rule_naming_no_live_file_is_refused` | 1 failed |
| The test's own package `__init__` not followed | the same | `…conftest_and_the_test_s_own_package…` | 1 failed |
| f-string module names not followed | the same | `…functions_strings_and_f_strings…` | 1 failed |
| Relative imports broken | the same | `…relative_import_is_followed`, and the brief's scheduler example on this repository | 2 failed |
| The original five plants, re-run on the rewritten file | the same | (floor 5, unmapped 3, functions 2, strings 1, conftests 1) | each red |
| The `$0` placeholder dropped from `sh -c '…' sh files…` | `OspreyFlow_Build/scripts/stack_lease.sh` | `…live_runs_exactly_the_selection…` (the start call run as the host runs it; a stand-in pytest records its argv) | 1 failed |
| Extra arguments after `--` dropped | the same | the same | 1 failed |
| A failed selection run anyway | the same | `…live_refuses_a_failed_or_empty_selection…` | 1 failed, once the test named the failed-selection message (the empty-selection refusal had caught it too) |
| `--base` not passed | the same | `…live_all_and_base_are_passed_to_the_selector` | 1 failed |

**Measured**, reproducibly: `process/lanes/admin/t1p3_measure.py 18` on main cf48b21, its output in
`gates/t1p3_measure.txt`. Over main's last 18 lane merges, ending d79b087, each merge's own diff selects
**184.5 of 291 live files on average (63%)**:
- 11 merges needed all 291;
- the other 7 needed 1, 11, 11, 1, 17, 68 and 11.

The full sets come from modules nearly every live test imports (`schemas/domain.py`, `ports/graph.py`,
`ontology/handling.py`, `harness/render.py`) and from paths the map leaves to the full set (`.gitignore`). An earlier
figure here, 178, came from a one-off script and did not match its own breakdown (my lane-reviewer's finding 3). The
plan's "13 merges" was the prototype's; both are superseded by this.

**Not delivered here:** the full set's nightly run on main. `stack_lease.sh live <lane> --all` runs it, and the
orchestrator schedules it (a carry).
