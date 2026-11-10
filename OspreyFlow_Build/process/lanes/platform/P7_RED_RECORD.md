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
| The cluster's Helm output unchanged | a YAML comment the shared claim's template emitted into the cluster's manifests (`gates/p7_renders_unchanged.helm-red.log`) | `gates/p7_renders_unchanged.py --helm main`: 0 differences after (`gates/p7_renders_unchanged.helm.log`) |
