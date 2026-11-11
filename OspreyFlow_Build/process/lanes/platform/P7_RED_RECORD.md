# Platform lane · P7 · red record (rule 15)

Recorded 10 November 2026, on the owner's Mac (Docker Desktop: Helm `alpine/helm:3.16.3` in a container),
offline on closed ports (every store port pinned to 1), no lane stack.

## `make cp-policy-check`: each branch of the check red alone (reviewer point 2)

Each branch of `tools/cp_policy_check.py` disabled at its own line in turn, the test that guards it run red, the
file restored (`git diff` empty afterwards). Each fault is planted where it would arise: in the values the chart
reads, or in Helm's own output (the shape a template edit would emit), so it fires alone. Each per-branch test
asserts that branch's own words, so a neighbouring branch cannot satisfy it.

| Branch | Plant (in the check) | Test (`tests/cp_policy_check/test_cp_policy_check.py::`) | Red |
| --- | --- | --- | --- |
| `hostPath` | `if "hostPath" in volume:` → `if False:` | `test_a_host_path_is_refused` | `set() == {'hostPath'}` |
| `runAsNonRoot` not true | the branch off | `test_run_as_non_root_false_with_a_numeric_user_is_refused`, `test_a_root_pod_is_refused` | 2 failed |
| no numeric `runAsUser` | the branch off | `test_a_named_uid_is_refused` | `'named-uid' in {'root'}` |
| `runAsUser` zero | `user <= 0` → `user < 0` | `test_uid_zero_is_refused` | `'root' in set()` |
| `privileged: true` | the branch off | `test_a_privileged_container_is_refused` | `set() == {'privileged'}` |
| `allowPrivilegeEscalation` | the branch off | `test_privilege_escalation_alone_is_refused`, `test_an_init_container_is_held_to_the_rules` | 2 failed |
| a capability added | the `or caps.get("add")` dropped | `test_a_capability_added_alone_is_refused` | nothing found |
| capabilities not all dropped | the `"ALL" not in drop` dropped | `test_capabilities_not_dropped_alone_is_refused` | nothing found |
| init containers checked | `initContainers` left out of the fields | `test_an_init_container_is_held_to_the_rules` | `[] == [('privileged', True)]` |
| `containerPort` < 1024 | the branch off | `test_a_container_port_below_1024_alone_is_refused` | `[] == [('low-port', 'containerPort 80')]` |
| a Service's `port` < 1024 | `port` left out | `test_a_service_port_below_1024_alone_is_refused` | `[] == [('low-port', 'port 443')]` |
| a Service's `targetPort` < 1024 | `targetPort` left out | `test_a_service_target_port_below_1024_alone_is_refused` | `[] == [('low-port', 'targetPort 80')]` |
| a foreign registry | the branch off | `test_a_foreign_registry_is_refused` | `set() == {'foreign-registry'}` |
| a `ReadWriteMany` claim | the PVC branch off | `test_a_read_write_many_claim_is_refused` | `set() == {'rwx'}` |
| a StatefulSet's `ReadWriteMany` claim template | the StatefulSet branch off | `test_a_stateful_set_s_read_write_many_claim_template_is_refused` | `[] == [('rwx', 'claim databases')]` |
| no deny-egress policy | the namespace check off | `test_a_namespace_without_the_deny_egress_policy_is_refused` | `set() == {'no-deny-egress'}` |
| a deny not covering every pod | the `all()` selector check off | `test_a_deny_policy_that_does_not_cover_every_pod_is_refused` | `set() == {'no-deny-egress'}` |
| a Dockerfile not `USER 10001:10001` | only a missing `USER` refused | `test_a_named_user_in_a_dockerfile_is_refused`, `test_main_fails_on_a_planted_fault` | 2 failed |

## The rest of this session's fixes, each test red before its fix

| Fix | Red before the fix | Test |
| --- | --- | --- |
| What a cluster's install writes into our Secret reaches the pods (ConfigMap, our Secret, the platform's) | 13 keys missing (development), 19 (production): `OIDC_JWKS_URL`, `MINIO_*`, `POSTGRES_SSLMODE`, the client secret, the reporting secrets… | `tests/harness/test_cloud_platform_render.py::test_every_key_a_cluster_s_install_writes_reaches_the_pods` |
| One password under two names is one `random_password` | no copies written | `…::test_a_password_the_install_writes_under_two_names_is_one_password` |
| S3 and STS by networks named, never the VPC's | no such hosts | `…::test_s3_and_sts_are_reached_by_networks_named_never_by_the_vpc_s` |
| The mail server an egress host | shown red again with its line removed (the first run failed on an unrelated schema refusal) | `…::test_the_mail_server_is_an_egress_host` |
| Connector hosts: the egress and the Conduit's allow-list from one list | no field | `…::test_a_connector_host_is_allowed_by_the_network_and_by_the_conduit_alike` |
| The GOV.UK assets route; a named certificate; the wildcard's depth | no paths, no `tlsSecret`, no refusal | `…::test_the_sign_in_page_s_govuk_assets_come_from_the_glass_on_its_own_host`, `…::test_a_certificate_secret_is_named_or_the_platform_s_is_used`, `…::test_a_host_the_platform_s_wildcard_does_not_cover_needs_a_certificate_named` |
| Every image to a repository the Terraform makes (a fake registry refusing as ECR does) | `_repositories` planted without init containers: `postgres:16.4` refused, the push stopped | `tests/cli/test_images_verb.py::test_every_image_goes_to_a_repository_the_terraform_makes` |
| Ours built for the platform's nodes | no `--platform` | `…::test_ours_are_built_for_the_platform_s_nodes` |
| A managed detail only to a container that read it on the cluster (init containers, Keycloak, LiteLLM included) | `reader=True` for every pod: the workspace given the database's password | `tests/harness/test_cloud_platform_render.py::test_only_the_readers_are_given_the_managed_stores_details` |
| The cluster's Helm output unchanged | a YAML comment the shared claim's template emitted into the cluster's manifests (`gates/p7_renders_unchanged.helm-red.log`) | `gates/p7_renders_unchanged.py --helm main`: 0 differences after (`gates/p7_renders_unchanged.helm.log`) |

## On the test server, 11 November 2026 (after the rebase onto main 9bcadc6)

Recorded on the test server (Linux, Docker; Helm `alpine/helm:3.16.3` in a container), offline on the closed
ports 59991–59994, no lane stack, no kind cluster. Each plant made alone in the working tree, the whole of its
test file run (so a neighbouring test cannot be the one that fires), the plant removed, `git status` showing
the harness and the check unchanged afterwards. The plant is in the code under test; each test's fault reaches
it the way the real call site does (the chart's values through Helm's own output for the check; a deployment
rendered through `render_cloud_platform` for the harness).

| Rule or fix | Plant | Test | Red (only this test failed in its file) |
| --- | --- | --- | --- |
| `cp-policy-check` refuses a numeric user other than 10001 (ADR-148 decision 3; reviewer point 16) | `elif user != UID:` → `elif False and user != UID:` | `tests/cp_policy_check/test_cp_policy_check.py::test_a_user_other_than_10001_is_refused` | `('other-uid', 'runAsUser is 1000, not 10001') in set()`; 1 failed, 28 passed |
| No `map:` refused in words | `if config.map is None:` → `if False and …` | `tests/harness/test_cloud_platform_render.py::test_a_deployment_without_a_map_is_refused_in_words` | `DID NOT RAISE CloudPlatformNotRenderable`; 1 failed, 58 passed |
| `GRANT <owner> TO CURRENT_USER` before `CREATE DATABASE … OWNER` (PG16, no superuser) | the `_grant_what_it_owns(container)` call removed | `…::test_a_database_s_owner_is_granted_to_the_login_that_makes_it[development]`, `[production]` | `AssertionError: keycloak-db`; 2 failed, 57 passed |
| The lock names only the images a pod runs | `and (engines or i.service not in GATEWAY)` removed | `…::test_the_lock_names_only_the_images_a_rendered_pod_runs[development]` | `locked but never run: ['litellm']`; 1 failed, 58 passed (production's fixture enables an engine, so its gateway runs) |
| An image with neither tag nor digest refused | `if not digest:` → `if False and not digest:` | `…::test_an_image_with_neither_a_tag_nor_a_digest_is_refused` | `DID NOT RAISE`; 1 failed, 58 passed |
| Two sources for one copy refused | `if held.get("source") != …` → `if False and …` | `…::test_two_sources_copied_to_one_target_are_refused` | `DID NOT RAISE`; 1 failed, 58 passed |
| Bucket names carry the Terraform's suffix | `aws_s3_bucket`'s name back to `"${var.namespace}-${each.key}"` | `…::test_bucket_names_are_unique_beyond_the_namespace_s_name` | `AssertionError` on `s3.tf`; 1 failed, 58 passed (a first attempt at this plant was a syntax error of mine, which failed the whole file at import; it proves nothing and is not counted) |

### After the lane-reviewer (11 November): the group rules, Jobs and CronJobs, the settings at every profile

Same conditions. Each new rule's test was written with it; each branch was then turned off alone and the whole
file run.

| Branch | Plant | Test | Red (only these failed in the file) |
| --- | --- | --- | --- |
| a Job's pod read (R1) | `"Job"` out of `POD_KINDS` | `test_cp_policy_check.py::test_a_job_s_pod_is_held_to_the_rules` | `[] == [('privileged…')]`; 1 failed, 33 passed |
| a CronJob's pod read (R2) | `"CronJob"` out of `POD_KINDS` | `…::test_a_cron_job_s_pod_is_held_to_the_rules` | the same; 1 failed, 33 passed |
| a CronJob's `jobTemplate` descended (R3) | `if kind == "CronJob":` → `if False and …` | `…::test_a_cron_job_s_pod_is_held_to_the_rules` | the same; 1 failed, 33 passed |
| `runAsGroup` not 10001 (R4) | the branch off | `…::test_a_group_other_than_10001_is_refused`, `…::test_a_container_s_own_group_alone_is_refused` | `'runAsGroup is 1000…' in {('other-gid', 'fsGroup is 1000…')}`; 2 failed, 32 passed |
| `fsGroup` not 10001 (R5) | the branch off | `…::test_a_group_other_than_10001_is_refused` | `'fsGroup is 1000…' in {('other-gid', 'runAsGroup is 1000…')}`; 1 failed, 33 passed |
| a supplementary group (R6) | the branch off | `…::test_a_supplementary_group_outside_its_allowance_is_refused` | `[] == [('supplementary-group'…)]`; 1 failed, 33 passed |
| group 0 for Keycloak alone (R7) | `allowed = {0}` for every pod | the same test | the same; 1 failed, 33 passed |
| the settings refused at every other profile (R8) | the schema's refusal off (`packages/schemas/deployment.py`) | `test_cloud_platform_render.py::test_the_settings_belong_to_the_profile_alone[cluster, local-lite, small]` | `DID NOT RAISE ValidationError`, 3 failed, 58 passed; each base is validated alone first, after a first draft whose cluster and small bases failed on other rules (rule 15) |
| `PROFILE_NAMES` holds the new profile | (found, not planted) | main's `tests/cli/test_named_deployments.py::test_the_profile_names_refused_are_the_schemas_profiles` | red in `make test` at `baaf6bf` (`gates/baaf6bfc.test.txt`) |

A Job is planted where one would really arise: the profile renders none today, so one is given in the values'
`jobs` and templated by the chart's own `jobs.yaml`. It is asserted clean before the fault goes in. The CronJob is
that Job wrapped as Helm would emit one.

Green before the plants, and again at the head after them: `make cp-policy-check` (the target as `P7_ci_makefile.diff` adds it, applied in the working
tree only): `development.yaml: 32 manifests, 0 violation(s)`, `production.yaml: 37 manifests, 0 violation(s)`,
then 91 passed (the check's tests, the rendered Terraform's and the render's) before the reviewer's points, and
98 after them (34, 3 and 61).

## Round 1 of the orchestrator's two reviews at 1a63953d (11 November 2026, test server)

Every fix this round, and the four older tests with no red of their own, each undone or planted **in the file the
fix lives in**, in the shape that code had (at 1a63953d) or emits, alone, then its tests run and the file written
back byte for byte (hash-checked): `gates/p7_round1_reds.py`, from OspreyFlow_Core, offline ports, no lease, nothing
else writing the tree. **32 plants, 32 red**, one only after its test was corrected (below). The green for each is
the full run at the head (`gates/<sha>.test.txt`).

| Item | Plant (file) | Red: the tests that failed |
| --- | --- | --- |
| 3 | a too-wide or default-route net passes (`tools/cp_policy_check.py`) | `test_a_host_s_network_that_opens_egress_is_refused` ×4, `test_managed_networks_that_open_egress_are_refused` |
| 3 | an Allow with no destination passes (same) | `test_an_allow_rule_with_no_destination_is_refused` |
| 3 | a Kubernetes egress rule to everywhere passes (same) | `test_the_open_egress_policy_is_refused` |
| 3 | `egress_nets` of any width (`packages/schemas/deployment.py`) | `test_a_network_that_would_open_egress_is_refused` ×5 |
| 3 | a platform's nets of any width (`harness/cloud_platform/settings.py`) | `test_a_platform_s_networks_that_would_open_egress_are_refused[managed_nets, service_nets]` |
| 4 | a pod no policy selects passes (check) | `test_a_dropped_internal_policy_leaves_pods_open_and_is_refused` |
| 4 | any namespace selector passes (check) | `test_a_widened_ingress_policy_is_refused`, `test_an_ingress_controller_namespace_not_the_platform_s_is_refused` |
| 4 | an address block passes (check) | `test_a_widened_ingress_policy_is_refused` |
| 4 | a rule from every source passes (check) | `test_the_public_policy_admitting_every_address_is_refused` |
| 4 | `ospreyflow-public` rendered behind the Ingress (`networkpolicies.yaml`) | `test_the_render_passes[development, production]` |
| 6 | the checksums unquoted, as at 1a63953d (`workloads.yaml`) | `test_helm_chart.py::test_a_checksum_of_digits_alone_is_still_text` — **not red at first**, see below |
| 7 | no timeouts; no body size; the cap's source bound at import (`harness/cloud_platform/__init__.py`) | `test_the_ingress_keeps_the_glass_s_websocket_open_and_takes_its_uploads` (×2), `test_the_ingress_s_settings_follow_their_sources` |
| 8 | no `fsGroupChangePolicy`, as at 1a63953d (`_helpers.tpl`); the rule off (check) | `test_the_render_passes` ×2; `test_a_volume_walk_at_every_start_is_refused` |
| 11 | no resources in the chart (`_helpers.tpl`); the rule off (check); none rendered; the heap not from the limit (`__init__.py`) | `test_the_render_passes` ×2; `test_a_container_without_resources_is_refused`; `test_every_container_asks_for_what_it_needs_and_is_limited` ×2; `test_arcadedb_s_heap_follows_its_memory_limit` ×2 |
| rulings | an image with no row is a bare KeyError; group 0 and the always-hosts as constants (`__init__.py`) | `test_an_image_of_ours_with_no_build_row_is_refused_in_words`; `test_a_door_group_zero_and_an_always_host_are_rows` ×2 |
| minor | another profile's config, an AttributeError (check) | `test_a_configuration_of_another_profile_is_refused_in_words` |
| 9 | the omitted image given `JAVA_HOME` (`services/api/Dockerfile`) | `test_the_omitted_image_does_not_declare_java` |
| older | the omission's stage made Java's (Dockerfile); the Conduit planned with Java (`profile.yaml`) | `test_the_cloud_platform_s_build_carries_no_java`; `test_the_conduit_is_planned_without_java` |
| 10 | the route that does not exist offered again (`services/api/map_admin.py`) | `test_on_a_cloud_platform_the_build_says_there_is_no_basemap_route_yet` (the older built-off-the-platform case, renamed) |
| minor | a provider block; no `:aud`; OpenSearch with no security group (`terraform.py`) | `test_the_providers_and_backend_are_the_namespace_folder_s` ×2; `test_the_bucket_role_trusts_the_service_account_s_tokens_for_sts_alone`; `test_opensearch_is_reached_…_alone` |
| older | a secret key the values read and the Terraform does not write (`terraform.py`) | `test_every_secret_the_values_read_is_one_the_terraform_writes` ×2 |

**The checksum test passed its own plant at first (rule 15's second paragraph).** The first all-digit digest the
test found was `0264289451781167`. Kubernetes' Go YAML reads it as a number; PyYAML, the test's reader, reads a
leading-0 string holding an 8 or 9 as text, so the unquoted template passed. The test now takes only a digest led by
1–9, which it asserts PyYAML reads as an integer; run again with the plant alone: red
(`test_a_checksum_of_digits_alone_is_still_text`, 1 failed).

**A defect found by its own test before any plant**: `upload_cap_bytes` took its source file as a default argument,
bound at import, so it would not follow the source (`'512m' == '2048m'`); the plant above restores that shape.

## Round 2 of the orchestrator's two reviews, and P7's own lane-reviewer (11 November 2026, the Mac and the test server)

The same script, `gates/p7_round1_reds.py`, now holds round 1's 32 plants and round 2's five, and counts a plant RED
only when **every** test it lists fails (it counted any failure before). Each failure's own text is printed in full.
Its whole output at the gated head: **`gates/p7_reds.0f17781b.log`, 37 plants, 37 red** (an earlier run at 20550ea6,
36 plants, is `gates/p7_reds.20550ea6.log`). After rebasing onto main a7bb34a, round 1's 32 are all still red.

| Item | Plant (file) | Red: the tests that failed, and why |
| --- | --- | --- |
| R2 1 | the Kubernetes egress `ipBlock.cidr` branch off (`tools/cp_policy_check.py`) | `test_a_kubernetes_egress_address_block_that_opens_egress_is_refused` ×4 (`0.0.0.0/0`, `::/0`, a /8, a /32): no violation at all ("expected 1, got 0"), so no other branch sees it |
| R2 1 | the Calico ingress Allow-beyond-a-selector branch off (same) | `test_a_calico_ingress_allow_beyond_a_selector_is_refused` ×3 (another namespace, nets, no source): no violation at all |
| self 2 | a Calico policy with no `types` read as no ingress policy (same) | `test_a_calico_ingress_allow_in_a_policy_with_no_types_is_refused`: no violation at all |
| R2 minor | the deployment's upload cap read as a bare `int` (`harness/cloud_platform/__init__.py`) | `test_the_ingress_reads_the_upload_cap_as_the_conduit_does` ×3 (`0`, `-1`, `lots`: `0 == 536870912` fails), `test_an_unset_or_empty_upload_cap_is_the_conduit_s_default` (a `None` traceback) |
| R2 5 | the Debian upgrade after the code, as `USER root` then `USER 10001:10001` (the shape at dd0233e1) (`services/api/Dockerfile`) | `test_the_final_stage_upgrades_before_the_code_and_as_root`: the final stage's first instruction is `RUN useradd`, not the upgrade |

The two plants of item 1 take the shapes Helm emits (a `to` rule in `ospreyflow-internal`'s egress; Calico's
`types` and an `ingress` rule on the allow policy, or a new Calico policy with ingress rules and no `types`), and each
test asserts exactly one violation, by the branch's own words. With the branch off, the check finds nothing, so the
red is that branch's alone. The edge each passes is its own green test (a /16 block, a selector-only source).
