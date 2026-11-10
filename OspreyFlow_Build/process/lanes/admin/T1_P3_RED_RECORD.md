# admin · T1 part 3 red record (10 November 2026)

Each check was planted out at its real call site, its test run red, and the file put back and green. These plants were
run by hand, one at a time. Offline: closed ports, no lane.

| Plant | File | Test | Red |
| --- | --- | --- | --- |
| No `live_select.py` (the tests written first) | `OspreyFlow_Build/scripts/live_select.py` | `test_live_select.py` | collection error |
| No route-rights floor | the same | `…graph_adapter_selects…`, `…empty_change_still_selects_route_rights`, `…rule_names_none_all_or_tests` | 3 failed |
| An unmapped path selects nothing | the same | `…path_no_rule_covers_selects_the_full_set`, `…removed_python_file_selects_the_full_set` | 2 failed |
| Imports inside functions not followed (`tree.body` for `ast.walk`) | the same | `…import_inside_a_function_and_a_module_named_in_a_string…` | 1 failed |
| Modules named in a string not followed | the same | the same | 1 failed |
| Conftest files not followed | the same | `…conftest_s_imports_count_for_every_test_beneath_it` | 1 failed |
| No `live` verb (the tests written first) | `OspreyFlow_Build/scripts/stack_lease.sh` | `test_stack_lease.py -k live_` | 3 failed |
| An empty selection not refused | the same | `…live_refuses_an_empty_selection…` | 1 failed |

**Measured over main's last 18 lane merges** (each merge's own diff, the map as committed): on average 178 of the 291
live files, about 61%. Seven of the 18 needed only a handful (1 to 10), two needed 56 and 226, and nine needed all 291. Those
nine changed modules that nearly every live test imports, such as `schemas/domain.py`, `ports/graph.py` and
`ontology/handling.py`; the map can do nothing for those, and part 2's per-test marks will.
