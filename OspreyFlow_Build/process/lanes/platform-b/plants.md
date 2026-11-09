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
