# P5b's red-then-green record (rule 15)

Each line is one plant: the code changed at the call site under test, the tests that went red
with it, and then the code restored and the tests green again. Plants were made with a script that
replaced one exact line and restored the file from a saved copy, run with the offline closed ports
(59991–59994, no lane) on this Mac. The test names are in `tests/` at the paths ADR-114
Amendments 37 and 38 give.

- answers: plant 'no difference check' -> test_server_backups_and_folders_backups_differing_is_refused red; plant 'no default' -> test_folders_backups_is_read_for_every_profile red
- backup: default_out_root -> REPO_ROOT/backups: 4 red (every_profile, falls_back, no_backup_inside, two_deployments); new_set_folder refusal removed: no_backup_inside red; main refusal removed: out_root_inside red; notice removed: falls_back red; no subfolder: 4 red; placeholder read as named: falls_back red; old server-only rule: 4 red
- update: old _backup_root (repo/backups off a server) -> test_an_updates_backup_is_never_written_inside_the_checkout and test_update_moves_a_self_contained_small red
- restore: old places not searched -> old_place red; old-first ordering -> looks_first red; checkout unfiltered -> another_deployment red; ADR-138 folder forgotten -> old_place red
- main dispatch: the old --out-root <folder>/backups line -> test_a_named_deployments_backup_goes_to_its_subfolder red
- install prompt: before the ask line -> test_install_asks_for_the_backups_folder red
- doctor: checkout not scanned -> left_in_the_checkout red; named old folders not scanned -> same red; Documents/Desktop dropped -> 2 params + link red; links unresolved -> link red; OneDrive dropped -> 2 Windows params red; placeholder read as named -> agree[raw1,raw4] red; everything warned -> plain red
- guided page: before the field -> 3 vitest red (saves/suggests/says); Review line removed -> Review test red
- restore path rule: a path-like argument that is no set went to the name lookup -> test_host_tools_reach_the_server::test_restore_answers_the_servers_names red (found, fixed)
- keyboard: Backups field removed -> setup-screens 'reaches Folders' red
- axe: Backups label removed -> install-page Folders (dark) red (label)
- review fixes (harness): checkout_root -> OspreyFlow_Core only: git_checkout red; spelling comparison: spelt_another_way red (case branch ran, not skipped, on this Mac); old SET_NAME: another_deployment (.incomplete) red; default_out_root -> REPO_ROOT/backups now reaches main and update: 7 red incl. falls_back (via main) and both update cases (fake refuses as the real backup does, nothing written to the checkout); blank read as named: falls_back red
- deployments: refusal removed -> 3 profile-name params red; refusal on every verb -> still_reached red
- review fixes (doctor): old SET_NAME -> left_in red; unreadable silent -> at_least red; no in-checkout check -> fails_the_doctor red; no case folding -> plain/link red; blank as named -> agree[raw3] red; answers not checked -> answers_before_install red
- answers placeholder refusal: test run before the refusal existed -> red
- Review: placeholder shown as a folder -> 'never chosen' vitest red
- second review (harness): abspath before resolve -> spelt_another_way (link + ..) and mirrors red; a climbing name accepted -> spelt_another_way red; placeholder by spelling -> falls_back (trailing slash) and agree[raw6] red
- second review (cli): a profile dropped from PROFILE_NAMES -> profile-name param and schemas_profiles red; checkout's deployment.name not refused -> checkouts_own_deployment_name red; relative folder against cwd -> inside_the_checkout red; no checkout read as the product -> off_a_checkout red; bad yaml raises -> unreadable_settings red
- second review (guided page): placeholder offered with no home -> 'never offers the placeholder' vitest red
- older gaps (orchestrator, 10 Nov): update's backup/restore without --config/--generated-root -> named_deployment_to_the_harness red ('no rendered deployment at …/deploy/generated/beta'); runbook Backups row verbatim -> runbook_names_the_folder red (placeholder printed); both tests run before the fix
- third review (update): the checkout's own given the rendered copy as --config -> never_written_inside_the_checkout and moves_a_self_contained_small red; a named deployment given --generated-root without --config -> named_deployment_to_the_harness red (its assertion, not a ValueError)
- third review (runbook): the folder expanded from ~ -> runbook_names_the_folder red (the renderer's home in the row); the placeholder always unnamed -> the same red (Small on a server of your own)
- guide carry: NOT_YET_IN_THE_GUIDE emptied -> test_every_answers_file_setting_is_in_the_guide[folders-*] red in both guides ('folders.backups is not in …'); restored
- gate (server make test at 5079bed): a server's setting left out read as no folder, its spelt-out default as its folder -> webapp_screens round trip [small] red (RUNBOOK.md differed); new every_profile case and doctor agree[raw8] red without each half of the fix; backup.py's docstring named the Build folder -> test_core_stands_alone red, reworded
- independent review (1): new_set_folder writing the unexpanded ~ -> tilde case red (set under cwd/~); main passing it unexpanded -> its second half red
- independent review (5): install without the backups checks -> install_checks_the_backups_folder red (the install went on); the test run before the fix
- independent review (2): the update's backup silent on the fallback -> never_written_inside_the_checkout red (no notice on stderr); the test run before the fix
- independent review (8): the git root's backups/ not looked in -> doctor git_roots red, restore git_roots red; (9) backups-synced as a failure -> 8 cases red (6 sync roots, the answers' doctor, the install), restored; (10) the case-sensitive branch replaces the skip (runs on the server's disk)
- independent review (6): guided page saving the placeholder off a server -> 'refuses the schema's backups placeholder' vitest red (onSave called); the test run before the fix
- preflight ports (after P5b): the check resolving against os.environ only -> own_graph_port red (2480 checked, the install refused as on the server); the env file over the shell -> the same red (2511 not checked); export kept, an inline comment kept, quotes kept -> as_compose red, each; all restored
- P6 (vitest): a composite read as one source -> gazetteers.test composite case red; none_built dropped -> the none-built case red; the Conduit's words shown on a 403 -> the refusal case red; Add/Remove drawn without run_pipelines -> the panel's no-right case red; the search not told of a change -> the panel's add case red; each restored
- P6 (after the review): the focused button disabled while busy -> the busy case red; a second press while busy -> red; no re-read after a failure -> red; the last case kept while another is read -> red; the search not asked again -> PlaceSearch asOf case red; a drawing told it reads a composite -> the drawn case red; each restored
- P6 (Playwright): the cases' registerCovered removed -> the coverage case red (both ids named); the busy button disabled again -> the add case red in Chromium (focus lost, 'inactive'); a too-faint token for the panel's state words -> axe color-contrast red in dark, light and GOV.UK (a 1:1 colour is left incomplete by axe, not failed, so not the plant used)
- ADR-147 Am 3: the read and match reverted to Amendment 1's -> 4 unit cases red (a case's own Location sent its osm_id; any type; matched on osm_id; a search by osm_id alone matching); live, stack g: the case's own place found by its osm_id and sent with osm_id and os_place_id (gates/am3-live-red.txt)
- ADR-147 Am 3, after the review (live, stack g, at ba7e215): builders.py alone reverted -> the exact search, the type-ahead and the adapter cases red, the read cases green; handling.py alone reverted -> the name/uprn read, the seed and decision 4's load match red, the match cases green; the matches-nothing step's fall-back (identity()) -> the shape case red (unit)
- P5b owed proof, the driver's conditions: no ID check in restore -> the another-lane case red; an old tag not put back -> the put-back case red; the after-check blind to a changed tag -> the after-check case red; another's volume allowed by the guard -> the guard case red; a teardown refusal raising -> the teardown case red; each restored
- P5b owed proof, after the first run: nothing held before the build -> the put-back case red (the old image pruned, no tag to put back); a hold left not failed -> the after-check case red; restored
- `p5b_deployment_guard.diff` (tests/harness/deployment_guard.py, the orchestrator's to apply): the GUARD_ARGV_ONLY exemption ignored → `test_every_teardown_in_the_tests_asks_first` and `test_a_guard_argv_only_file_passes_only_while_it_starts_no_process` red; its process check ignored → the latter red. Restored: green.

## T2

- Item 3, `apps/workspace/keyboard/registryCoverage.test.ts`: the constant-shape case written before the scan read constants → red (`reads a name passed through a string constant`). Fixed scan, with `packs.spec.ts` rewritten to `const REGISTRY = "PACKS_ACTIONS"; assertAllCovered(REGISTRY, …)` (the real call site's shape) → 63 green. Same spec, the constant branch planted out → 3 red: the constant case, `every assertAllCovered call … names its registry in a way this scan reads` (its words: "packs.spec.ts: REGISTRY", and the fix), and `PACKS_ACTIONS is asserted`. Spec restored.
- Item 2, `tests/local_docker_guard.py`: the inner session (switch on, a stand-in `docker` that records being started) run before the plugin was wired into `tests/conftest.py`'s `pytest_plugins` → red: the stand-in started ("info"), the child's refusal missing. Wired → 15 green. The `PATH` stand-in planted out → red ("1 failed, 3 skipped": a child process reached the stand-in). Restored: green. On this Mac (switch present, PATH without the real docker): `test_image_references.py` skipped at collection, `test_workspace_proxy.py` skipped in words; `test_images_built_fresh.py` and `test_lanes_launch.py`'s fake-docker cases unchanged (the latter's one failure is the same with the switch absent).
- Item 1, `apps/workspace/keyboard/playwrightPorts.test.ts`: written before any config moved → red, every config: admin and case on the same ports (5184, 5185, 5183, 5186; the harness's 5191–5194 and 7217–7220). Configs on `lanePort` → 17 green. Planted: case given admin's slot in `lane_ports.tsv` → 8 red (every config, and the whole-table check); the keyboard config back to a literal 5185 → its case red. Restored: green.
- Item 1 on the server (the orchestrator's ask: lanes' copies run side by side there, with no git and no OSPREY_LANE offline): `test_stack_lease.py`'s offline and remote export cases asserting `OSPREY_PORTS_LANE=case` → red before `stack_lease.sh` exported it, green after (44). `lanePorts.ts` not reading it → 8 red in `playwrightPorts.test.ts` (each config's "two lanes' offline runs on the server never share a port", and the lookup case); reading it → 24 green.
- Fix pass (both reviews). Core no longer names Build or reads the table (`test_core_stands_alone.py` green): `lanePorts.ts` reads `$OSPREY_PORTS_SLOT` alone, set by `stack_lease.sh` and `lanes_launch.sh` (diff) by the lane's exact row. Red first: `test_stack_lease.py`'s slot cases (case → 2; admin-ddl and admin-b → `unlisted-…`, never admin's 1) → 4 red, then 46 green; `lanes_launch` (diff `t2_lanes_launch.diff`, applied here and reverted): the session's `OSPREY_PORTS_SLOT="10"` for studio → red without the launcher's export, 28 green with it. Planted: `inLinkedWorktree` always false → the worktree case red (d2b-scratch branch and a detached head built in a scratch repo); `keyboard.spec.ts` back to a literal 5185 → the literal-scan case red; `tests/test_lane_ports.py` with case on admin's slot and docs' row gone → both its table cases red ("case's 5283 is also admin's"; "['docs']"). registryCoverage: the let, shadowed-constant, comment and template cases → 4 red, then 67 green. The guard: `_WRAPPERS` emptied → the `env`/`sudo`/`timeout` shapes red; a real Python child's own `docker info` refused by the PATH stand-in (green; red when the stand-in is off, as before); its folder removed at unconfigure (`test_the_guard_puts_back_what_it_changed`).

## UPG fix (ADR-114 Amendment 39, option A)

- `tests/test_refresh_before_the_gateway.py` against main's `scripts/refresh.py` → 8 red: both v0.4.12 shapes not refused (folder changed), update's files step, the list form, no gateway, the unheld salt, the volumes, the words; `start --build`'s case reached a docker call there and was skipped on this Mac (it runs on the server). With the fix → 9 green, 1 skipped here (Compose's own `config -q`, server-only).
- Planted: the salt check off → the list-form case red (the v0.4.12 cases stay green: the generic check refuses them too, by design); the generic check off → the unheld-salt case red; the volume declaration off → the volumes case red. Restored: green.
- The minting attempt (fa4fa8e/0b45910) is withdrawn: the rehearsal's run 2 failed it, and both reviews found it the wrong shape.
- Re-review fixes (07fc398 →). The stage made 700 before anything is copied in; planted world-readable → `test_the_stage_is_private_while_the_pass_runs` red. The move into place by `os.replace`, `deployment.env` last; planted back to in-place copies → `test_an_interrupted_move_into_place_…` red. The deployment an update is moving, found by its rollback point when `--files-only` is named none (v0.4.12's update names none; the rules lane confirmed it in code); planted out → both discovery cases red; today's `update` names it (`OSPREYFLOW_DEPLOYMENT_DIR`), planted out → `test_todays_update_names_its_deployment_to_the_files_step` red. Fixture: `OSPREY_RELEASE_VERSION=v0.4.12`, a held `OSPREY_MODEL_KEY_GEMINI` kept through a refusal, workspace's own Dockerfile path.
- The marker is v0.4.12's own (`rollback/<version>-<UTC stamp>/` holding `.commit`; 964a2a9 `harness/update.py` 278-287, called at 430). On the owner's shape (three kept by name and the checkout's own): planted "any recent folder counts" → `test_on_the_owners_shape_only_the_deployment_under_way_is_reached` red; planted "no hour window" → the same red. Restored: 17 green, 1 server-only skip.
- Delta and re-review fixes (a9f5c69 →), each planted red then restored: the salt check's call removed → `test_the_salt_check_alone_refuses_…` (the v0.4.12 shape with the gateway secrets held, which the generic check passes) and `test_start_build_…` red; both checks off → `test_start_build_says_the_refusal_in_words_and_starts_nothing` red (it now records `subprocess.run`, which the old `_run` patch never reached); every file renamed → `test_a_file_a_service_mounts_on_its_own_keeps_its_inode` red; future stamps allowed → the `[future]` case red; `ValueError` not caught → the `[20261399T000000Z]` case red; refusing with no gateway → `test_no_gateway_is_no_refusal_on_its_account` red (its first red, against main, was only an `AttributeError`); `deployment.env` moved first → `test_an_interrupted_move_into_place_…` red. `test_with_no_update_under_way_the_checkouts_own_is_found_as_before` is a regression guard (it passed against main too), not a red. `tests/harness/test_store_volumes.py`'s three `refused_move` cases went red under the generic check (their fixture held no secrets); the fixture now holds them, 24 green.
- On the server at 431521b (`gates/upg-run1-431521b.txt`): v0.4.12 rendered from 964a2a9's own tree is identical to `fixtures/deployment_v0_4_12/` (compose.yaml with its image and build lines aside, Caddyfile, glass.json); deployment.env differs only in the fixture's deliberate `OSPREY_RELEASE_VERSION=v0.4.12` (the bare render says `dev-unknown`) and its held values. `test_compose_itself_accepts_the_refreshed_project` and `test_start_build_says_the_refusal_in_words_and_starts_nothing`: green at the head; red with main's `scripts/refresh.py` ("service \"api\" refers to undefined volume map-settings: invalid compose project").
- Run 3's (b) found `ospreyflow apply` restarting the gateway with `--no-deps` before the new `litellm-db` step ever ran ("P1000: Authentication failed … for `litellm`"). `test_a_service_the_new_render_adds_is_started_with_its_dependencies_first` (a deployment installed without `litellm-db`, reapplied): red before the fix (no whole-project `up`); green after; planted out → red. 90 green across the apply, ingest-upload and store-volume tests.
- The delta review of 11e92f4: the stand-in Compose now starts in `depends_on` order and refuses a run-once step a `--wait` up starts that nothing waits on (the ollama-models incident). Planted: no such refusal → `test_the_stand_in_compose_refuses_a_run_once_step_nobody_waits_on_as_compose_does` red; no dependency order → `test_a_service_the_new_render_adds_…` red (litellm-db no longer before litellm); the failed start not worded → `test_a_failed_start_says_the_settings_are_written_and_how_to_start_them` red; profiles not left out → `test_an_added_service_with_a_profile_starts_nothing_on_its_own` red. 92 green across the apply, ingest-upload and store-volume tests.
- Run 3 (rules, a9f5c69): `ospreyflow start --name osprey-upg` after the failed first apply recovered the deployment (litellm-db exited 0, the role made, 12 healthy, the gateway's master key equal to the Conduit's, GET /v1/models 200), which is why the words name `start`.
- Run 4 (rules, live on ospreyflow-test, a fresh v0.4.12 at d85f514; evidence `/root/osprey-runs/rules-upg/logs/05{a,d,e}-*.txt`, `05-apply-1.log`): (a) the refusal, 43 of 43 files unchanged; (b)'s first `ospreyflow apply --name osprey-upg` exited 0, litellm-db ran, 12 healthy, the gateway's master key equal to the Conduit's by hash, GET /v1/models 200; the key move said "not moved… stay in deployment.env" on v0.4.12's api, as expected. **The whole-project up recreated api, litellm, ner, report-sync, superset and workspace, and made litellm-db; no store was recreated** (postgres, arcadedb, opensearch, valkey kept their container IDs and identical named-volume mounts; no volume emptied; rows identical: 3 cases, 2 datasets, 2 rules, 1 saved pattern; postgres-data 79 → 109 MB, the gateway's database; opensearch-data 812 → 720 KiB, its container untouched).
- Run 4, the rest (rules; logs committed by rules under `process/lanes/rules/gates/upg-run4/`): `ospreyflow update` said "Already at v0.4.12; nothing to do" (no newer release exists), so the release's pull was stood in for by `harness.apply --build` (12 healthy, verify 3/3; it moved the key into the gateway); the second `ospreyflow apply` said "no model key to move". (c) today's files step twice, with the deployment named: 43 of 43 files unchanged. (d) seven migrations, each re-run writes 0. End state: no `OSPREY_MODEL_KEY_*` left, `KEYS_IN_GATEWAY=yes`, the gemini key present in the gateway; 77 of 77 secrets held at v0.4.12 byte-identical (only the moved key went, with `OSPREY_MODEL_ENGINES` and `OSPREY_RELEASE_VERSION`); the gateway's master key equal to the Conduit's, GET /v1/models 200; a Ledger rule made under v0.4.12 raised an alert after the upgrade. **Not proven:** api and workspace on a v0.5.0 lock's digests, and `update`'s real pull, pin and rollback (no release exists yet: owed by one real `ospreyflow update --name` after the tag); the checkout's own deployment's plain path (ii) (the box's osprey-small holds 2480), covered by the unit cases.

## Carries (lane/platform-b-carries, 11 November 2026)

- The chart's checksum annotations (the merger's find): `test_a_checksum_that_reads_as_a_number_is_still_a_string_kubernetes_takes` sets `environment` to `{OSPREY_PROBE: "2354"}` (its sha256 prefix is `3625796312017304`, all digits) and renders through `helm template` and kubeconform. Red on the server before `| quote` (the annotation came back as the int 3625796312017304); green after, 20 of 20 chart tests on the server. Audit: the two `workloads.yaml` lines were the chart's only unquoted hashes (`jobs.yaml`'s sits inside a `printf` name).
- `write_private`, atomic: a write failing part way left the old file truncated, red; a run under sudo not given the old owner, red; both green after. The 600 case passed before, so it is a guard.
- The staged refresh's edges, each red first in `tests/test_refresh_carries.py` and planted red after: the pending restarts (a run that dies after the move), the owner kept on the move, the stage glob, the lock, a symlinked `compose.yaml`, `export` lines, the shell. The symlink case was first written on `litellm.yaml`, which passed for the wrong reason (a mounted file is written in place), so it moved to `compose.yaml`. `test_refresh.py`'s `--files-only` case now expects the owed restart once.
- The lockout's words: `ospreyflow stop` asked Compose anyway, red; apply's port lookup asked Compose anyway, planted red. The CLI's copy and the harness's are held to the same answers on the required, unset-only, plain, defaulted and escaped forms, the shell and `export` lines.
- Lint: the touched Build tests tidied of I001, RUF028 and ISC004; 132 green after.

### Carries, after my own lane review (11 November 2026, on the test server, offline)

Each new test written against the reviewed code, then each fix planted back out at its call site
(`/tmp/p11plants/plant.py` and `carries_plants.py`: replace, run, restore); every one red for its
stated reason, green with the fix.

| Plant | Fault put back | Red |
|---|---|---|
| A1 | `store_volumes.put_back` rewriting `deployment.env` in place | the witness link saw the rewrite (`test_put_back_replaces_…`) |
| A2 | `apply.move_into_place` copying `deployment.env` with `copytree` | the same (`test_apply_s_move_into_place_replaces_…`) |
| R1 | refresh counting a value in the shell as held | `test_a_value_only_in_the_shell_is_not_held`: `[] == ['OSPREY_LITELLM_SALT_SECRET']` |
| R2 | the lock on the files pass alone | `test_the_lock_is_held_through_the_build_and_the_restarts`: free at build, up and restart |
| R3 | the lock opened for writing | `test_the_lock_file_is_opened_read_only` |
| R4 | a stale stage left by another account not said | `FileExistsError` instead of words |
| R5 | `--files-only` clearing the record | `test_files_only_leaves_the_restarts_owed`: no record |
| R6 | a stores refusal dropping what an earlier run owed | `test_a_stores_refusal_keeps_…`: no record |
| R7 | a bare rename (no owner kept, the link replaced) | `…keeps_its_owner`: nothing given an owner; `…symlinked_deployment_env…`: not a link |
| U1 | `update` never clearing the record | `test_an_update_clears_the_record_after_its_restarts` |
| H1 | `checksum/files` unquoted | `9266205751740302 == '9266205751740302'` (the files probe `{"probe.txt": "420"}`) |
| H2 | a ConfigMap key unquoted | Helm: "unsupported map key of type: <nil>" (`NULL`) |
| C1 | `_compose_of` not checking | stop, start, logs, status, uninstall each answered 0 or asked Compose |
| C2 | `switch` with no label fallback | `switch` answered 1 |

The parity case gained a quoted value, an unquoted ` #` comment and an empty shell value; the comment
case was **red against both readers**, the CLI's copy and the shared `read_env_file` alike (`X= #
note` read as `# note`), and both were fixed. The owner cases now give the old file an owner the
runner is not (4242), so a version taking the runner's or the new file's owner fails. Earlier counts
corrected: "20 of 20 chart tests" is `test_helm_chart.py`'s 20 collected (12 functions, parametrised);
"132 green" named no file set and is withdrawn in favour of the counts in `SERVER_LOG-carries.md`.

The lane review's table above holds **14 plants** (A1–A2, R1–R7, U1, H1–H2, C1–C2), not the 16 the
report and friction row said.

### Carries, after the orchestrator's review of c5209b1 (11 November 2026, on the Mac, offline)

Each case written red first against c5209b1, or, where its first red was only a missing name or a
setup error, shown red again by a plant of the real defect at its call site (copy, replace, run,
restore; every plant removed, `grep -c PLANT` 0 after each). Offline, closed ports, on the Mac.

| Plant | Fault | Red |
|---|---|---|
| O1 | the three in-place writers (as at c5209b1) | `test_env_writers_whole.py`: the scan named all three (before `ALLOWED` gained `_put_back`, which then hid it: see L2); each writer's hard-link witness saw the rewrite (5 failed) |
| O2 | the Redactor hiding our own words (as at c5209b1; then `if False:` for the new branch) | `test_refusal_words_reach_the_operator.py`: start --build's two refusals and update's line hidden (5 failed); planted, 3 failed: the gateway and update cases named no variable, so passed without the branch (see L3) |
| O3 | `FilesHeld` skipping a symlink (as at c5209b1) | `test_refresh.py::…symlinked_file_through_its_link[compose.yaml, deployment.env]`: the target kept the refresh's bytes. **The test was then lost** (the round set aside with `git diff`, `checkout` and `apply` brought back only `store_volumes.py`) and committed without it; restored at L1 |
| O4 | the owner taken from the staged file (`_owner_of(Path(staged))`) | with the path-keyed stand-in, both owner cases red; with c5209b1's any-path stand-in, the same plant **passed** |
| O5 | the lock made under umask 077, an unreadable lock (as at c5209b1) | `…lock_file_is_644_whatever_the_umask`: 600; `…cannot_open_is_said_in_words`: PermissionError |
| O6 | backup, restore, update, demo add, repair-sign-in unguarded (as at c5209b1) | `cli/test_compose_lockout.py`: those five red; map, grading, models green already (guarded, now tested) |
| O7a | update not locked whole (`contextlib.nullcontext()`) | `test_update_apply.py`: refused-while-held and held-for-the-whole-update red |
| O7b | no descriptor handed to the files child | the child refused its own parent: "another refresh or update … is under way" |
| O7c | any descriptor believed (the identity check removed) | `…descriptor_named_that_is_not_the_lock_holds_nothing` red |
| M1 | the lockout words with no shell mention (`emptied = []`) | `…shell_sets_empty_is_said_to_be_the_shell_s` red; the `--name` and `xargs -r` cases red against c5209b1 |
| M2 | refresh's move writing in place (`target.write_bytes`) | the now-unconditional symlink witness red |
| M3 | deployment.env moved into place 644 (as at c5209b1) | `…moved_into_place_is_600`: 644 |

`test_the_lock_file_is_opened_read_only` failed on the Mac before any change of this round (its spy
took no `dir_fd`, which macOS's `rmtree` passes); fixed with the round. `start --build` is left out of
the lockout case on purpose: it hands to refresh, whose own refusal O2 holds.

### Carries, after my own lane review of the round (11 November 2026, on the Mac, offline)

| Plant | Fault | Red |
|---|---|---|
| L1 | `FilesHeld` skipping a symlink, planted back (`and not path.is_symlink()`) | the restored `test_refresh.py` case, both parameters |
| L2 | `_put_back`'s own `shutil.copy2(item, directory / item.name)` put back on the real tree | the gate (`test_no_module_writes_an_env_file_in_place`, `test_the_gate_flags_c5209b1_s_put_back_copy`): `ALLOWED` now names the helper that refuses an env file, not `_put_back` |
| L3 | the Redactor's branch removed (`if False:`) | the update case, now driven by the real `--files-only` child naming `OSPREY_POSTGRES_PASSWORD`, red with the rest (5 failed) |
| L4 | the name-in-prose rule (as at c5209b1's round) | four lines shown with a value: `OSPREY_POSTGRES_PASSWORD is hunter2`, `…, hunter2`, `(OSPREY_X_SECRET) hunter2`, a child's `… was hunter2` |
| L5 | the shell clause after "deployment.env does not hold" | `…shell_sets_empty_is_said_to_be_the_shell_s`: the file was said to lack a value it held |
| L6 | `start --build` unguarded for a shell-emptied value | `test_start_build_refuses_a_value_the_shell_sets_empty`: refresh ran |
| L7 | the lock's creation unguarded | `test_a_lock_this_account_cannot_make_is_said_in_words`: PermissionError |
| L8 | update's arguments matched as whole tokens | `test_an_update_that_asks_no_compose_is_not_refused[--make-bundle=b.tar]`: refused |


### Carries, after the orchestrator's review of ad4bef7 (11 November 2026, on the Mac, offline)

| Plant | Fault | Red |
|---|---|---|
| A1 | the redactor's phrase rule (as at ad4bef7) | three still-hidden shapes shown: a value after our phrase, an upper-case value among the names, a value after our whole sentence; and `secret-lab`'s and `token-test-2`'s refusals hidden |
| A1b | the gateway sentence's copy drifted (` (drift)` planted) | `…variable_is_shown[secret-lab, token-test-2]`: the copy is held to refresh's own words |
| A2 | `_inherited`'s flock half planted out | `test_a_stale_open_of_the_lock_itself_holds_nothing`, the only case that sees it |
| A4 | put-back's own `deployment.env` branch planted out | the writer scan **stays green**; `test_put_back_replaces_deployment_env_rather_than_rewriting_it` goes red: the scan's limit, now in its docstring |
| M1 | the rollback point made with the umask's mode (as at ad4bef7) | `…rollback_point_is_private…`: not 700 |
| M2 | `state/` another account's (as at ad4bef7) | `…state_folder_this_account_cannot_write…`: PermissionError |

### Carries, after the orchestrator's confirmation of b2feedf (11 November 2026, on the Mac, offline)

| Plant | Fault | Red |
|---|---|---|
| B1 | the advice exemption by next character (as at b2feedf, and on main) | `test_an_exempt_name_with_a_value_after_it_stays_hidden`: all eighteen (three names, six shapes: `"NAME": "v"`, `NAME v`, `NAME ghp_…`, `NAME is v`, `set NAME to v`, `NAME v on this machine…`) shown |
| B2 | any upper-case name with an underscore taken as a variable (`_VARIABLE` planted back) | `…value_shaped_like_a_variable_among_the_names_stays_hidden[HUNTER_2, SECRET_VALUE_9]` shown |
| B3 | update's step and version slots open (the earlier pattern planted back) | `test_update_s_slots_take_only_their_own_words[step, version]`: `'hunter password'` and `v0.5.0hunter` shown |
