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
| Ruling 1: a plain GPL-2.0 Java refused | `licence_check._CLASSPATH` loosened to `^gpl-2\.0` | `tests/licence_check/test_runtime_licences.py::test_any_other_gpl_java_is_refused` | 4 of 6 cases (plain GPL-2.0, GPL-2.0-only, another exception, the exception AND GPL-3.0) |
| Ruling 1: the exception for the recorded runtime alone | `runtime_allowed`: the exception for any runtime | `…::test_the_exception_is_for_the_recorded_runtime_alone` | `other-vm` passed |
| Ruling 1: an undeclared Java refused | `find_runtime_offenders`: the Java detection off | `…::test_a_java_runtime_the_image_does_not_declare_is_refused` | `[] == [('api', 'java', 'undeclared')]` |

After the lane's review (development live run on stack c under the platform lease, 06:10–06:20 UTC):

| Fix | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| Review 1: an addition is the dataset's, seen by every case reading it | `app._case_gazetteers_view`: only the adding case's records | `test_case_gazetteers_routes.py::test_the_addition_is_the_dataset_s_so_every_case_reading_it_sees_it` | `assert False is True` |
| Review 2: a rebuild never writes into a dataset no longer there | `case_gazetteers.refresh_cases`: the dataset check off | `…::test_a_rebuild_refreshes_each_dataset_and_drops_one_no_longer_there` | `{'case-a', 'deleted-ds'} == {'case-a'}` |
| Review 3: a confirmed copy is kept (and a link is no reason, rule 3) | `remove_copies`: the confirmation not judged | `…::test_removing_reverts_the_gazetteer_s_own_copies_and_never_another_writer_s` | the confirmed copy reverted |
| Review 4: a failed re-add keeps the earlier record | `add_case_gazetteer_route`: the record removed on any failure | `…::test_a_failed_copy_again_keeps_the_earlier_addition` | `[] == [('case-a', …)]` |
| Review 5 and 8: a case load's write keeps a copy one, through the real upsert (live) | `merge.merge_provenance`: the incoming write's `gazetteer` alone | `test_case_gazetteer_copies_live.py::test_a_case_s_load_writing_onto_a_copy_keeps_it_a_copy_and_the_case_s` | `gazetteer=None`, `osm_id` on the read |
| Review 10: a rebuild for another unit refused | `map_places.check_unit`: the first build's unit not judged | `test_geospatial_admin_routes.py::…_before_anything`, `test_gazetteer_dataset_registration.py` (2) | 3 failed |
| Review 12: each way a Java enters an image, alone | `_JAVA_IN_IMAGE`: the package alternative never matching; then `jlink` dropped | `test_runtime_licences.py::test_a_java_runtime_the_image_does_not_declare_is_refused` | the three package cases; then the `jlink` case |
