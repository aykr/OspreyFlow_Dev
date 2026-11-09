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

After the orchestrator's independent review (offline; live on stack a under the platform lease, 08:11–08:30 UTC):

| Item | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| 1: a rebuild never writes over what a case asserted (live and offline) | `copy_places`: the case's own copies not left out of the writes | `test_case_gazetteer_copies_live.py::test_a_rebuild_after_a_case_s_load_keeps_what_the_case_wrote`; `test_case_gazetteers_routes.py::test_a_rebuild_never_writes_over_what_a_case_asserted` | the gazetteer's `Ashwell` over the case's spelling |
| 2: `copies_kept` counts only what the asker may read (live and offline) | `remove_dataset_gazetteer_route`: every kept copy counted | `test_case_gazetteer_routes_live.py` (a SECRET copy the case's load wrote); `test_removing_reverts_…_keeps_the_case_s` | `copies_kept` 2 to an OFFICIAL Author |
| 3: the gazetteer's unit is the dataset's | `_dataset_and_gazetteer`: the unit not judged | `test_another_unit_s_gazetteer_is_refused_in_words` | 200 |
| 6: a dataset-level right | the `run_pipelines` dependency dropped from `PUT` | `test_without_run_pipelines_nothing_is_added` | not 403 |
| 7: a copy a case's link rests on is kept, the layers read too (live and offline) | `remove_copies`: links read in the dataset alone | `…::test_a_removal_keeps_a_copy_a_case_s_link_rests_on_in_the_dataset_or_a_layer`; offline the same | the layer-linked copy reverted |
| 8: every declared runtime label read | the old anchored, double-quoted pattern | `test_runtime_licences.py::test_a_declared_runtime_is_read_however_its_label_is_written` | all six layouts passed silently |
| 8: `git` not passed silently | the git detection off | `…::test_git_installed_and_undeclared_is_refused` | `[] == [('api', 'git', 'undeclared')]` |
| 10: no gazetteer node id in a copy's source | the locator `place <node id>` | `test_adding_copies_each_place_into_the_dataset` | the id in the copy |
| 12: a unit holding only a gazetteer holds nothing | `units_held` counting gazetteer datasets | `test_gazetteer_dataset_registration.py::test_a_unit_holding_only_a_gazetteer_holds_nothing` | `unit-9` held |

**The orchestrator's ruling (d) on item 7, and the lane's review of round 2** (offline unless said; live on stack a under the platform lease, 08:27–08:37 UTC, and the stack released at the orchestrator's word, the machine's swap full). Ruling (d) replaces item 7's rows above: a removal deletes nothing.

| Fix | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| (d): a removal answers and leaves the same whatever rests on a copy | the build before (d), as committed at `6313d29` | `test_case_gazetteers_routes.py::test_a_removal_tells_the_author_the_same_whatever_rests_on_a_copy` | `'1 place stays…'` against `None`; the copy reverted in one and not the other |
| (d): a removal deletes no copy and stops its refresh | the same | `…::test_removing_keeps_every_copy_with_its_mark_and_stops_its_refresh` | the copy reverted |
| (d): the place search leaves a removed gazetteer's copies out | `is_gazetteer_place`: the removal record not judged | `test_map_places_route.py::test_a_removed_gazetteer_s_copies_are_no_longer_offered` | Cranwell offered |
| Review 3: another unit's gazetteer answered as none | `_dataset_and_gazetteer`: 409 for another unit's | `…::test_another_unit_s_gazetteer_is_refused_as_one_that_does_not_exist` | the two answers differ |
| Review 4: a failed copy keeps its record | the record removed on failure | `…::test_a_failed_copy_keeps_the_record_so_the_copies_written_can_be_removed` (2) | `[] == [('case-a', …)]` |
| Review 6: one dataset's failed refresh said alone | `refresh_cases`: the failure not caught | `…::test_one_dataset_s_failed_refresh_neither_stops_the_others_nor_the_build` | `RuntimeError` out of the refresh |
| Review 11: `git`'s exemption pinned to its Dockerfile and licence | the exemption by runtime name alone | `test_runtime_licences.py::test_git_declared_is_named_as_awaiting_the_owner_never_passed_silently` | `git` under AGPL passed |
| Review 11: every run names it | `main()`: the awaiting lines not said | `…::test_every_run_names_what_awaits_the_owner` | no line |
