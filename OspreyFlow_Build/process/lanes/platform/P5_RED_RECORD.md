# Platform lane · P5 · red record (rule 15)

Each fix removed at its own call site, the test run red, the fix restored and the test green. Offline
runs on the closed ports (59991–59994), no lane set.

| Fix | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| Ruling 8: the build's unit, checked before anything runs | `app.build_basemap_route`: `gazetteer_unit = "unit-1"`, the check skipped | `test_geospatial_admin_routes.py::test_the_build_s_unit_is_a_setting_and_an_unknown_one_is_refused_in_words_before_anything` | `assert 200 == 422` |
| Ruling 6: a removal never reverts a copy another writer also wrote | `case_gazetteers.remove_copies`: every copy taken as the gazetteer's alone | `test_case_gazetteers_routes.py::test_removing_reverts_the_gazetteer_s_own_copies_and_never_another_writer_s` | the written copy reverted |
| Ruling 6: … nor one a link rests on | `remove_copies`: the links read but not used | same test | the linked copy reverted |
| Ruling 6: a copy's provenance names its gazetteer | `case_gazetteers._copy`: `gazetteer=None` | `test_adding_copies_each_place_into_the_case_s_own_dataset` | `assert None == 'gazetteer-osm-rutland'` |
| Ruling 6: a copy's identifiers withheld, keyed on its provenance (live, stack a under the platform lease) | `handling.is_gazetteer_held`: the dataset prefix alone | `test_case_gazetteer_copies_live.py::test_no_copy_s_identifier_is_sent_on_any_node_read` | `osm_id` and `uprn` on the node read |
| Ruling 6: the place search offers a copy (live) | the same plant | `…::test_a_case_finds_its_copy_of_a_place_by_name_at_its_point` | `[] == [(copy, 'Ashwell')]` |
| Ruling 6: decision 3b for a copy, at the store (live) | `builders.match_any_field`: the provenance clause dropped from the guard | `…::test_the_case_s_own_searches_never_match_a_copy_by_an_identifier` | the copy found by its `osm_id` |
| Ruling 6: decision 3b for a copy, at the routes (live) | the same plant | `test_case_gazetteer_routes_live.py::test_a_case_that_adds_a_gazetteer_reads_copies_without_identifiers_and_still_loads` | `/search` by the `osm_id` answered the copy |
