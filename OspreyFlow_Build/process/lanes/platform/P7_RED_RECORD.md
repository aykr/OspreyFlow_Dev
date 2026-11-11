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

Green before the plants, and again at the head after them: `make cp-policy-check` (the target as `P7_ci_makefile.diff` adds it, applied in the working
tree only): `development.yaml: 32 manifests, 0 violation(s)`, `production.yaml: 37 manifests, 0 violation(s)`,
then 91 passed (the check's tests, the rendered Terraform's and the render's).
