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
| Review 3 (superseded by ruling (d): a removal reverts nothing) — a confirmed copy is kept | `remove_copies`: the confirmation not judged | `…::test_removing_reverts_the_gazetteer_s_own_copies_and_never_another_writer_s` | the confirmed copy reverted |
| Review 4: a failed re-add keeps the earlier record | `add_case_gazetteer_route`: the record removed on any failure | `…::test_a_failed_copy_again_keeps_the_earlier_addition` | `[] == [('case-a', …)]` |
| Review 5 and 8: a case load's write keeps a copy one, through the real upsert (live) | `merge.merge_provenance`: the incoming write's `gazetteer` alone | `test_case_gazetteer_copies_live.py::test_a_case_s_load_writing_onto_a_copy_keeps_it_a_copy_and_the_case_s` | `gazetteer=None`, `osm_id` on the read |
| Review 10: a rebuild for another unit refused | `map_places.check_unit`: the first build's unit not judged | `test_geospatial_admin_routes.py::…_before_anything`, `test_gazetteer_dataset_registration.py` (2) | 3 failed |
| Review 12: each way a Java enters an image, alone | `_JAVA_IN_IMAGE`: the package alternative never matching; then `jlink` dropped | `test_runtime_licences.py::test_a_java_runtime_the_image_does_not_declare_is_refused` | the three package cases; then the `jlink` case |

After the orchestrator's independent review (offline; live on stack a under the platform lease, 08:11–08:30 UTC):

| Item | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| 1: a rebuild never writes over what a case asserted (live and offline) | `copy_places`: the case's own copies not left out of the writes | `test_case_gazetteer_copies_live.py::test_a_rebuild_after_a_case_s_load_keeps_what_the_case_wrote`; `test_case_gazetteers_routes.py::test_a_rebuild_never_writes_over_what_a_case_asserted` | the gazetteer's `Ashwell` over the case's spelling |
| 2 (superseded by ruling (d): no count) — `copies_kept` counts only what the asker may read (live and offline) | `remove_dataset_gazetteer_route`: every kept copy counted | `test_case_gazetteer_routes_live.py` (a SECRET copy the case's load wrote); `test_removing_reverts_…_keeps_the_case_s` | `copies_kept` 2 to an OFFICIAL Author |
| 3: the gazetteer's unit is the dataset's (the test since renamed `…_refused_as_one_that_does_not_exist`, below) | `_dataset_and_gazetteer`: the unit not judged | `test_another_unit_s_gazetteer_is_refused_in_words` | 200 |
| 6: a dataset-level right | the `run_pipelines` dependency dropped from `PUT` | `test_without_run_pipelines_nothing_is_added` | not 403 |
| 7 (superseded by ruling (d), below) — a copy a case's link rests on is kept, the layers read too (live and offline) | `remove_copies`: links read in the dataset alone | `…::test_a_removal_keeps_a_copy_a_case_s_link_rests_on_in_the_dataset_or_a_layer`; offline the same | the layer-linked copy reverted |
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
| Review (round 2) 5: the copier reads as the dataset's unit (live) | `_reader` with the system unit (the build at `6313d29`) | `test_case_gazetteer_copies_live.py::test_a_restricted_case_load_on_a_copy_is_still_the_case_s_at_a_rebuild` | `_copies` in `copy_places` read as unit `system` (stack d, under the platform lease, 17:35–17:40 UTC): the gazetteer's `Ashwell` over the case's `Ashwell (restricted)`; restored, 9 passed |
| Review (round 2) 7: every page written (live) | — (a check, not a plant: it asserts all 2,000 copies) | `…::test_a_region_is_copied_in_bounded_pages_and_timed` | — |
| Review (round 2) 9: a real reference-mode load links, a refresh after it writes no second set (live) | — (positive control at the real call sites) | `…::test_a_real_case_load_then_a_refresh_keeps_one_copy_and_its_links` | — |
| Review (round 3) 2: the place search's records a dependency | the `getattr` fallback to no exclusion | `test_map_places_route.py::…_removed_gazetteer_s_copies…`, `…::test_without_the_gazetteer_records_the_search_refuses_rather_than_offer_removed_copies` | both |
| Review (round 3) 3: a refresh failing outright never fails the build | `_settle`: the guard catching nothing | `test_geospatial_admin_routes.py::test_a_refresh_that_fails_outright_neither_fails_the_committed_build_nor_hides_it` | the build failed |
| Review (round 3) 9: a removal needs only its record | `DELETE` through `_dataset_and_gazetteer` | `test_case_gazetteers_routes.py::test_a_removal_needs_only_the_record_not_the_gazetteer_s_state_now` | 404 |
| Review (round 3) 12: a re-add is the re-adder's | the in-memory store keeping the first record | `…::test_a_re_add_is_recorded_as_the_re_adder_s` | `author-1` |
| Review (round 3) 11: `git-core` and a copied `git` binary | the regex without them | `test_runtime_licences.py::test_git_installed_and_undeclared_is_refused` | passed silently |

**The orchestrator's review sending P5 back (round 3).** Offline unless said. Live on stack d under the platform lease, run on the server (`stack_lease.sh remote`, detached), 18:29–20:25 UTC, logs under `osprey-runs/platform.meta/runs/20261109T18*`. Each plant is one line at its call site (`adapter.py` at the line named), restored with `git checkout` after its run.

| Fix | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| 1: the console's Build sends the unit | `GeospatialScreen` sending no unit | `GeospatialScreen.test.tsx` "sends the region and the unit typed" | called with `("rutland", "")` |
| 1: the console's fake runner refuses what the Conduit refuses | `_Runner` accepting any argv (the fake before) | `test_webapp_geospatial.py::test_the_fake_runner_refuses_a_build_without_a_unit_as_the_conduit_does` | exit 0 for a build without `--unit` |
| 1: a build without a unit refused in words, nothing run | `build_basemap_step`: the unit not judged | `…::test_build_basemap_without_a_unit_is_refused_in_words_and_runs_nothing` | 200, not 422: the empty unit passed the fake's parse and the runner was reached (the status assertion, before the `runner.calls` one) |
| 6: a gazetteer's addition audited before its copy | `audit.record` after `copy_places` | `test_case_gazetteers_routes.py` (the failed-copy case) | no `add_dataset_gazetteer` entry |
| Minor: only a place the gazetteer's dataset holds alone | the filter `gazetteer in p.datasets` | `…::test_only_a_place_held_by_the_gazetteer_s_dataset_alone_is_copied` | the shared place copied |
| 4: `get_node` (live) | `adapter.py:780` `node_from_element_map(results[0], None)` | `test_case_gazetteer_copies_live.py::test_no_copy_s_identifier_is_sent_on_any_node_read` (also `…_keeps_it_a_copy_and_the_case_s`) | `osm_id` and `uprn` on the read. The route test stayed green: node detail at the route is the seed, through `get_nodes` |
| 4: `get_nodes`, node detail at the route (live) | `adapter.py:830` `(record, None)` | the same, and `test_case_gazetteer_routes_live.py::test_a_case_that_adds_a_gazetteer_reads_copies_without_identifiers_and_still_loads` (the seed) | both: the bulk read, then the seed's delta, carried `osm_id`/`uprn` |
| 4: store search (live) | `adapter.py:929` `(r, None)` | both tests (search by name; `/search` at the route) | the identifiers on what was found |
| 4: suggest, by name (live) | `adapter.py:961` `(r, None)` | both tests: the new suggest-by-name assertions (`Ashwe`; `NAME[:5]` at `/suggest`) | the identifiers on the suggestion |
| 4: expansion (live) | `adapter.py:1006` `(r, None)` | both tests (`expand`; `/expand` at the route) | the identifiers on the arrived copy |
| 4: the working set's own projection (live), not counted | `working_set/service.py:402` `withhold_sources` dropped | the route test | green: the adapter had already withheld them. The second layer is defence in depth, and no read path depends on it |
| 5: the port contract's conformance case, `PORT_CONTRACT.diff` applied (live) | none | `test_suite.py::test_a_gazetteer_copy_matches_a_case_reader_on_its_name_alone` | green, 1 passed |
| 5: the same, the search guard's copy clause dropped | `builders.py` `off_gazetteer` without `{copied}` | the same | `search_nodes("osm-conf-4411")` found the copy |
| 5: the same, the suggest projection dropped | `adapter.py:961` `(r, None)` | the same | `osm_id`, `uprn` on the suggestion |

After the plants, with the diff applied: `test_route_rights.py`, the whole graph-port conformance suite, both copy files, `test_gazetteer_ids_withheld_live.py` and `test_gazetteer_place_search_live.py` gave **372 passed** (1 h 43 m). The tree was then restored, and only the commit's own files were left changed.

**Round 3, items 2 and 7, and the retract minor.** The image was built and scanned on the test server under the platform lease on stack d (`gates/p5_image_check.sh`, through `stack_lease.sh remote`), 20:26 and 20:35 UTC. Images were tagged `osprey-p5-*` and removed at the end of each run. The retract test ran live at 20:41 UTC.

| Fix | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| 2: does trivy see the jlinked runtime? | the same image built from `eclipse-temurin:21.0.1_12-jdk` (October 2023, with known CVEs) | `make trivy-image-api`'s own `trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed` | **not red: exit 0**, as for the current image. trivy lists 118 Debian, 12 jar and 58 Python packages, and no package of the runtime itself (its 12 `jar` entries were not listed by name; the script's filter matched no name with java, jdk or openjdk in it) (`gates/360c83c.image-old-pin.txt`). The gap is recorded, and the version check below stands in it |
| 2: the version check over that same old image (the real call site) | the label as committed (`21.0.13+9`); then the label set to the image's `21.0.1+12` | `tools/java_runtime_check.py --image … --latest` | exit 1 both times: "the image's /opt/java/release names 21.0.1, its Dockerfile 21.0.13+9" with the build drift; then "Temurin 21.0.13+9 is out and the image pins 21.0.1+12". Green over the repinned image (`gates/360c83c.image-repinned.txt`) |
| 2: the check's own branches (offline) | each branch removed in turn: the newest compared, the `/opt/java/release` drift, the build drift, a release file or `java -version` naming none, Adoptium's empty answer, a second label, a label of no Temurin shape, versions compared as text | `tests/licence_check/test_java_runtime_check.py` | each plant fails its own case alone. The first draft read `JAVA_RUNTIME_VERSION`, which `jlink` does not write: the real image showed it, and the input was redrawn from the image's own output (rule 15) |
| 2: the pin against October 2026's update | — (a check against Adoptium) | `java_runtime_check --latest` at the old pin | "Temurin 21.0.13+9 is out and the image pins 21.0.12.1+1". Repinned to `21-jdk@sha256:ebfbb18d…` (21.0.13+9, 29 October) |
| 7: planetiler run by the image's Java (amd64) | — | `java -jar planetiler.jar --help` (v0.10.2, sha256 `f310bd04…`) | exit 0 at the new pin. The first run's exit 1 ("Unable to access jarfile") was the script's 0700 temporary directory against the image's uid 10001, not the runtime; it was fixed in the script |
| Minor: a retracted copy stays a copy, withheld (live) | `writer._replacement_for` dropping `provenance.gazetteer` | `test_case_gazetteer_copies_live.py::test_a_retracted_copy_is_still_a_copy_and_its_identifiers_still_withheld` | `None == 'gazetteer-osm-rutland'`; restored, 1 passed |

**The lane's own review of round 3.** Offline, at the commits after `eaae0fa`. Each plant is at its call site and restored after its run.

| Fix | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| Defect 5: every read path withholds, rule 4 (the nine call sites not shown red live, and any later one) | `adapter.py` each of `find_node:880`, `suggest_locations:936`, `list_nodes:983`, `_hydrate_paths:1068` (`paths`), `match:1103`, `most_connected:1187`, `busiest_links:1211` and `:1212`, `recently_confirmed:1264`, `shared_contacts:1302` given `None` in turn | `tests/adapters/graph_arcadedb/test_every_read_withholds_by_its_principal.py::test_every_read_in_the_adapter_withholds_by_its_caller_s_principal` | each names its own method and line, `(…, 'None')`. The live reds above show that the withholding a principal triggers works at five of these sites |
| Defect 6: Adoptium's answer, read through `_latest` and `main` | `main`'s guard narrowed to `(OSError, ValueError, KeyError)`; the `releases` list check removed; the unshaped-name refusal removed; the User-Agent dropped | `test_java_runtime_check.py::test_main_refuses_whenever_adoptium_cannot_be_read` (`incomplete`, then `null`), `…_release_name_of_no_temurin_shape…`, `…_sends_a_client_name` | a traceback for `IncompleteRead`; a pass on `releases: null`; the unshaped name passed; no client name |
| Defect 6: the image unreadable | `main`'s image guard catching nothing | `…::test_main_refuses_an_image_it_cannot_read_in_words` | `CalledProcessError` out of `main` |
| Defect 13: the label read as `licence-check` reads labels | round 2 item 8's anchored, double-quoted pattern | `…::test_the_label_is_read_however_it_is_written` | all four layouts |
| Defect 7: any unit the Conduit can name | the strict pattern before | `test_webapp_geospatial.py::test_any_unit_the_conduit_can_name_is_sent_and_its_own_refusal_shown` | "Major Crime" refused |
| Defect 7: a null unit is none | `str(body.get("unit", ""))` | `…::test_build_basemap_without_a_unit_is_refused_in_words_and_runs_nothing` | `--unit None` sent |
| Defect 7: a unit read as an option | the leading-`-` guard removed | the same | `-x` and `--by` sent as the unit |
| Defect 9: the fake refuses an unknown unit as the Conduit does | the fake's unknown-unit branch removed | `…::test_any_unit_the_conduit_can_name…` | exit 0 for `unit-9` |
| Defect 12: the ruling and carry said on every run | `AWAITING_OWNER`'s text without the ruling | `test_runtime_licences.py::test_every_run_names_what_awaits_the_owner` | the dulwich and L1.7 assertions |
| Defect 1: Core stands alone | the Makefile line (`5d3281e`'s parent) | `tests/test_core_stands_alone.py` | both of its cases, as the reviewer read them; green once removed |
