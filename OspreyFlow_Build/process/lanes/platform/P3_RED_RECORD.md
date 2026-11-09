# Platform lane · P3 · red record (each new test shown red by a plant at its real call site)

## Carried from P2's independent review (commits e56300a, a1f9adc, 41c7ff3)

| Test | Plant | Red |
| --- | --- | --- |
| `tests/adapters/model_litellm/test_stand_in_gateway_usage.py::test_a_key_given_models_is_refused_any_other_model_in_the_measured_words` | the stand-in's models check removed | 1 failed |
| `…::test_the_key_list_is_hashes_newest_first_a_hundred_a_page_at_most` | the stand-in's size cap raised to 1000 | 1 failed |
| `tests/services/api/test_model_engine_keys.py::test_a_changed_master_key_revokes_every_engine_key_the_new_one_would_not_derive` | the reconcile's revoke removed | 1 failed (and the paging case) |
| `…::test_one_engine_s_key_is_refused_on_another_engine_s_models` | `models` not sent with the engine's key | 1 failed |
| `…::test_every_page_of_the_gateway_s_keys_is_read_before_revoking` | the first page of `/key/list` alone | 1 failed |
| `…::test_a_garbled_first_answer_never_stops_the_conduit_starting` | the first `start` catching only `ModelAdminRefused` | 1 failed |
| `…::test_an_empty_master_key_derives_no_engine_key` | `GatewayAdmin`'s blank-master check removed | 2 failed |
| `…::test_a_hosted_engine_named_local_is_refused` | the `local` name check removed | 1 failed |
| `…::test_test_the_connection_is_tagged_as_the_engine_s_test_job` | the tag not passed | 1 failed |
| `apps/workspace/src/patterns/QueryBuilderPanel.test.tsx` › shows an engine's limit reached in the Conduit's words | `model_limit_reached` misspelt in `patterns/api.ts`'s list | 1 failed |

## Measured first (rule 15), the pinned gateway (`ghcr.io/berriai/litellm@sha256:d295634e…`), a stand-in provider, no hosted provider called

- Platform lease on stack a, about 20:45:50–20:46:32 UTC: a key made or updated with `models` is refused any
  other model, held or not, 403 `key_model_access_denied`, naming the allowed models, never the key;
  `/key/update` changes `models` at once. `GET /key/list` answers SHA-256 hashes, newest first;
  `return_full_object=true` adds `token` (the hash), `key_name` (`sk-...` and the last four), `metadata`;
  `size` at most 100 (422 above); `total_count`, `current_page`, `total_pages`. `POST /key/delete` takes a
  hash (200; an unknown hash 404); the deleted key's next call is 401.
- Platform lease on stack a, 20:52:21–20:54:02 UTC: after three calls with an engine key (and about 75 s),
  its SHA-256 is in `LiteLLM_VerificationToken` (left out of every backup) and in `LiteLLM_SpendLogs`,
  `LiteLLM_DailyTagSpend` (which the usage reads), `LiteLLM_DailyUserSpend` and `LiteLLM_DailyTeamSpend`.

## Item 3 run live, item 5 written (resumed session, 8 November 2026)

Platform lease on stack a, taken 21:00:51 UTC, released 21:10:54 UTC; the pinned gateway and the stand-in
provider on networks of the lane's own (`plat-p3-net`, `plat-p3-pub`), its own database `litellm_p3`
(dropped after), `OSPREY_LIVE_GATEWAY_URL=http://127.0.0.1:54400`:

| Test | Plant | Red |
| --- | --- | --- |
| `test_model_gateway_live.py::test_the_real_pg_dump_leaves_out_every_sealed_row_of_the_real_gateway` (live) | `LiteLLM_DailyTagSpend` taken out of the tables allowed to hold the key's hash | 1 failed, naming `LiteLLM_DailyTagSpend` **and `LiteLLM_DeletedVerificationToken`** |
| `tests/harness/test_gateway_backup.py::test_a_backup_holds_no_engine_key_of_the_gateway` | a deleted engine key's row planted in `LiteLLM_DeletedVerificationToken`, before the table was left out | 1 failed |

**A green that was not one.** The first live run (21:04:19–21:05:37) passed on a fresh gateway, which had
deleted no key. The plant's run, the second on that gateway, found the hash also in
`LiteLLM_DeletedVerificationToken`: the first run's `finally` had deleted the engine key, and the next run
derives the same key (an HMAC of the engine's name). So the check passes on a first run and fails on any
later one, as a deployment would after its first engine removal or revocation (rule 15: the plant must meet
the dependency in the state the real call site meets it). The table is now left out of every backup; live
again at 21:09:25–21:10:42 on the same gateway, the deleted keys present: 1 passed.

## Part 2, maps administration (ADR-147), offline, closed ports

Each plant applied to the file under test, the named tests run, the file restored
(`scratchpad/plant.py`); a Glass plant restored by copy.

| Test | Plant | Red |
| --- | --- | --- |
| `test_tile_proxy.py` (new WMTS-key cases) | `MissingMapKeyError` not yet defined | collection error |
| `test_tile_proxy.py` | the key not appended to the WMTS request; the Admin key not used first | 3 failed each |
| `test_map_admin.py::test_an_area_over_the_tile_cap_is_refused_with_its_count` | the cap check removed | 1 failed |
| `…::test_a_changed_address_drops_the_key_held_for_the_old_one` | the address check never true | 1 failed |
| `…::test_a_failed_run_is_said_in_fixed_words_without_the_key_or_the_address` | `str(error)` for the words | 3 failed |
| `…::test_a_run_fetches_each_missing_tile_once_with_the_admin_key` | the cache read skipped; the key not given | 1 failed each |
| `test_map_admin.py` (both 600 cases) | `fchmod(0o644)` | 2 failed |
| `…::test_a_provider_that_takes_no_key_refuses_one` | the `needs_key` check removed | 1 failed |
| `…::test_the_schedule_is_due_every_so_many_hours_and_the_scheduler_runs_it` | the scheduler never runs a due area | 1 failed |
| `…::test_each_provider_s_tier` | every local file tier 1 | 1 failed |
| `…::test_a_build_on_a_small_synthetic_region_registers_a_tier_1_provider` | the provider not registered | 1 failed |
| `test_map_admin_routes.py::test_every_maps_route_refuses…` | `manage_geospatial` removed from the areas route | 1 failed |
| `…::test_a_planted_key_is_in_no_response_log_audit_or_maps_file` | the refusal's words `str(invalid)` | 1 failed |
| `…::test_the_tile_proxy_carries_the_admin_key_upstream_and_nowhere_else` | the route not given the Admin key | 1 failed |
| `…::test_the_map_follows_a_change_in_admin_with_no_restart` | `get_map_config` reading the start-up config | 1 failed |
| `test_geospatial_admin_routes.py::test_build_basemap_route_takes_no_server_path_from_the_glass` | the body read leniently (extra fields dropped) | 1 failed |
| `tests/harness/test_map_settings_render.py` | (written before the renderer change) | 2 failed |
| `tests/harness/test_map_settings_backup.py` | (written before the backup and restore code) | 3 failed |
| `tests/test_conduit_image_java_licence.py` (then asserting the Java runtime was in the image; renamed and inverted after the review, below) | the Java runtime's `COPY` removed | 1 failed |
| `tests/cli/test_map_verb.py` | `built/` not made; the verb run on the host; a non-jar taken | 1 failed each |
| `tests/harness/test_webapp_geospatial.py` | (written before the change; the 501s); the region check removed; the before-Launch check removed | 4 failed; 1 failed each |
| `apps/harness/keyboard/setup-screens.spec.ts` › Build and Verify | the region dropped from the build's body | 1 failed |
| `tests/test_demo_osprey_config_is_tier_1_only.py::test_no_maps_file_is_committed…` | a `maps.yaml` planted in the index (`git add -N`) | 1 failed |
| `keyboard/admin-maps.spec.ts` | one case's `registerCovered` removed; the schedule's change doing nothing | 1 failed each |
| `src/admin/AdminSections.test.tsx` | (Maps added to `sections.json` before the expected list) | 1 failed |
| `tests/services/api/test_admin_sections.py::test_every_admin_route_is_some_section_s` | (the geospatial routes' "no screen" exemption, now untrue, still listed) | 1 failed |

**Greens first, then a red at the real call site (rule 15).** `test_map_admin.py`'s sixteen cases and
the routes' seven passed on their first run, so each was then shown red by the plants above, each at the
line the real caller reaches. **Measured offline:** the Conduit image's Java stage (`docker build --network
none --target java`, the cached `eclipse-temurin:21-jdk`): `jlink` first failed (`/opt/java` already exists
in the JDK image), then built a runtime of 100 MB whose `java -version` answers 21.0.12.1. The full image
was not built: its other stages fetch packages.

## Live, `test_route_rights.py` (the orchestrator's request)

Platform lease on stack a, taken about 21:56:40 UTC, released 21:57:48 UTC: `test_route_rights.py` 4 passed
(P2's `models_admin_limits_route` and `models_admin_usage_route` and the eleven Maps routes in
`ROUTE_RIGHTS`); with `maps_admin_prefetch_route`'s entry removed, 1 failed ("in the app, not the table").

## Accessibility, `a11y/every-harness.spec.ts` on `maps-harness.html`

The first scan found two button names not containing their visible text (2.5.3, `label-content-name-mismatch`:
"Make the default" named "Open the map on …", "Add an area" named "Add a prefetch area"), in the dark,
light and GOV.UK themes: 15 failed. Fixed in the names (and the keyboard spec's); the harness's `open=area`
then matched the button by its text, so the area form is scanned open: 20 passed (five states, three themes,
and 2.5.3's own check per state).

## Live, the files the change reaches (Prompt L)

Platform lease on stack a, taken 22:02:15 UTC, released 22:03:22 UTC, at the rebased branch:
`test_route_rights.py`, `test_tile_cache.py`, `test_prefetch.py` and `test_statelessness.py` (the Conduit's
real lifespan in uvicorn subprocesses: the Maps admin, its Postgres audit and the schedule made at start),
17 passed in 44 s; `map_admin_audit` then present in the stack's `ospreyflow` database. Not run: the restore
and bundle exit tests (`tests/harness/test_restore_exit_test.py`, `test_bundle_exit_test.py`), which need a
real deployment, and this lane never starts one (`make dev-up` is the owner's).

## After the lane's own review (lane-reviewer, 8 November 2026)

Two blockers and the must-fix items; each new test red first (written before the fix), then each
fix's own plant at its real call site (offline, closed ports, unless named live).

| Test | Plant | Red |
| --- | --- | --- |
| `test_tile_key_in_no_log.py` (a real loopback provider answering 200, 403 and 500; the real `_http_get`, route and logger) | (before the fix: httpx logged every tile URL, key included, at INFO, and the `HTTPStatusError` named it) | 4 failed |
| `…` | the `httpx`/`httpcore` filter not installed | 3 failed |
| `…` | `raise_for_status()` back in the fetch | 2 failed |
| `test_map_admin_routes.py` (Admin names no `env:` reference, no address inside the deployment, no key on a browser-fetched provider) | (before the check) | 21 failed |
| `…` | the `env:` check removed; the IP check removed; the dotless-name check removed; the browser check removed | 4, 5, 3 and 1 failed |
| `test_map_admin.py::test_a_key_is_given_only_to_the_address_it_was_entered_for` | the address comparison removed from `key_for` | 1 failed |
| `…::test_a_provider_the_conduit_does_not_fetch_refuses_a_key` | the profile/browser check removed | 1 failed |
| `…::test_a_maps_file_that_cannot_be_read_leaves_the_map_on_osprey_yaml_s` | the fallback removed | 1 failed |
| `…::test_adding_a_provider_records_each_of_its_fields` | only the tier recorded | 1 failed |
| `…::test_a_build_with_no_java_or_no_jar_is_refused_before_anything_is_downloaded` | the early refusal removed | 1 failed |
| `tests/harness/test_ingest_uploads.py::test_the_tiles_folder_s_built_door_is_given_to_the_conduit_before_up` | (before `prepare` covered every door) | 1 failed |
| `tests/harness/test_map_settings_backup.py::test_a_restore_puts_the_maps_file_back_private` | (written for the atomic write first) | 1 failed |
| `tests/harness/test_map_settings_backup.py::test_a_backup_takes_the_maps_file_and_never_a_map_key` | the backup reading `map-keys.yaml` | 1 failed |
| `tests/services/api/test_prefetch_follows_admin.py` | `effective_map` reading `osprey.yaml` alone | 1 failed |
| `tests/test_conduit_image_java_licence.py` | the Java stage back in the Dockerfile | 1 failed |
| `tests/cli/test_map_verb.py::test_build_places_the_jar_and_says_where_the_build_runs` | the words not naming the Conduit | 1 failed |
| `test_map_admin_routes.py::test_a_holder_of_manage_geospatial_alone_manages_the_maps` | the build route's admin-role check removed | 1 failed |
| `keyboard/admin-maps.spec.ts` › a provider's key is entered | the request sending `{"key": ""}` | 1 failed |
| `tests/ingest/test_map_admin_build_end_to_end.py` (live: platform lease on stack a, 22:23:22–22:23:59 green, 2 passed; 22:24:11–22:24:45 red) | the failed build's transaction committed | 1 failed |

**A red that was not one, caught at once:** the first plant of the live build case ran through the
offline runner (closed ports), so its "2 failed" was the store being unreachable, not the plant; it was
run again under the lease with the leased ports, red for the right reason.

## After the orchestrator's independent review (8 November 2026)

| Test | Plant | Red |
| --- | --- | --- |
| `test_map_admin_routes.py::test_an_installer_s_key_never_follows_an_edit_to_another_host` (the reviewer's plant exactly: `env:OS_DATAHUB_API_KEY` pointed at `attacker.example`) | (before the fix) / the address check on an installer's key removed | 1 failed / 1 failed |
| `…::test_a_maps_file_written_outside_admin_never_moves_an_installer_s_key` | (before) / the `env:` removal in `_vetted` removed / `config()` not vetting | 1 failed each |
| `…::test_the_host_check_is_not_bypassed` (`1{z}7.0.0.1`, a `{z}` port, `127.1`, `0x7f.1`, `169.254.43518`, `2130706433`, `postgres.`, `keycloak.`) | (before) / the raw host-placeholder check removed / `inet_aton` fallback removed / the trailing-dot strip removed | 7 failed / 1 / 3 / 2 failed |
| `…::test_a_name_that_resolves_inside_is_refused_at_save` (five answers, the resolver stood in) | (before) / the save-time lookup removed | 5 failed each |
| `…::test_a_name_that_resolves_inside_by_the_time_of_a_fetch_is_not_fetched` | (before) / the route's `refuse_inside` removed | 1 failed each |
| `test_tile_key_in_no_log.py::test_a_key_is_taken_in_the_query_alone` (path, port, host, fragment) | (before) / the schema's query rule removed | 4 failed each |
| `…::test_a_secret_in_a_url_s_path_reaches_no_log_record` (the real fetch, the real loggers) | (before) / the redaction back to the query alone | 1 failed each |
| `…::test_a_secret_in_a_url_s_port_is_a_fetch_failure_that_names_no_url` | (before) / `InvalidURL` not caught | 1 failed each |
| `…::test_each_http_client_logger_drops_what_a_url_carries_past_its_host` | the filter on `httpx` and `httpcore` alone, not its children | 3 failed |
| `test_map_admin_routes.py::test_a_key_typed_into_the_address_is_refused_pointing_to_enter_key` | the key-shaped-parameter check removed | 3 failed |
| `…::test_the_schedule_is_six_hours_a_day_or_a_week` | `every_hours: int` | 4 failed |
| `test_map_admin.py::test_a_run_is_paced_so_a_provider_is_not_flooded` | the pause removed | 1 failed |
| `test_tile_key_in_no_log.py::test_a_tile_larger_than_any_tile_is_refused_and_not_kept` (a loopback provider answering 5 MB) | the cap removed | 1 failed |
| `test_demo_osprey_config_is_tier_1_only.py::test_a_conduit_with_no_maps_file_serves_exactly_this_config` | a tier-2 OS Open Zoomstack provider added to the committed `osprey.yaml` (restored at once, never staged) | 1 failed (the open-licence cases still passing) |
| `test_geospatial_admin_routes.py::test_build_basemap_route_rolls_back_and_reports_a_real_failure` | the error's own words sent to the Glass | 1 failed |
| `…::test_the_places_are_committed_before_the_provider_is_registered` | `settle` never called | 1 failed |

**A first green that was not one:** the pacing case first passed with no pause in the code, because its
area was a single tile, so "one pause fewer than the tiles" was zero; the area was widened and it failed,
then passed with the pause. **Measured:** no record of httpcore's own loggers carries a URL past its host on
a real fetch (their connection record names host and port), so a real fetch cannot show their filter red;
a record made as httpx makes its own does.

**A rule 14 slip, contained (23:49 UTC).** Under a lease on stack b the run exported stack a's ports from
habit while the admin lane held stack a. The port guard refused it at start-up ("Nothing was collected and
no connection was made", repeated with `--collect-only` to confirm), so nothing reached admin's stack. The
ports are now taken from the acquire's own export line. **Live after the review round:** on stack b
(23:52–23:53) and on stack c (23:53:36–23:54:49) every case that writes to an object store failed
`INTERNAL_FAILURE` on `UploadPart`: Docker's disk was full (310 MB free of 197 GB). Stack c's Postgres also
held `LinkTypeProposal` rows with a status `main`'s schema does not have (another lane's). Neither is the
branch's; the run waits for space. Before the disk filled, the same live files passed whole on stack a.
