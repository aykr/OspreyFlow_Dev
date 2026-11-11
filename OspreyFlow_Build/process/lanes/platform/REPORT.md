# Platform lane · P7 · report (11 November 2026, test server; round 1 of the orchestrator's two reviews at 1a63953d)

P7 is rebuilt at **dd0233e1** (tree `8af3ee5b`), on main 9bcadc6 (main has not moved), the schemas commit at its head. Every must-fix
(1–11) and every minor is fixed or carried below, each refusal red first (`P7_RED_RECORD.md`, last section: 32 plants, 32 red). The
kind cluster was not needed and is down (0 `osprey-p7-*` containers). Nothing of mine is running. Nothing was pushed.

| Item | State | Proof |
| --- | --- | --- |
| 1 `make docs-pdf` | Cannot run here: this server's Chromium prints "ﬁgures" (U+FB01), which `tools.docs_pdf` does not match; read back with pypdf. Guide restored to main's by name, its change sent as `P7_admin_guide.diff` | `test_docs_pdf` passes at the head; the merger applies the diff, remakes the PDF, runs both |
| 2 gates at the head | `make test`: 4 failed, 10978 passed, each explained below. `make -k ci`: **green** (workspace rebuilt `--no-cache --pull`: 0 HIGH/CRITICAL). `cp-policy-check`: 0 violations, 136 passed | `gates/dd0233e1.{test,ci,cp-policy-check}.txt` |
| 3 egress by one setting | Refused at /16 (IPv4: AWS's largest VPC) and /48 (IPv6: one site), default routes above all, in `osprey.yaml` and a platform's settings; `open-egress` in the check; §3c names `managed_nets` (the client's whole VPC; narrow it) | `test_a_network_that_would_open_egress_is_refused`, `test_a_host_s_network_that_opens_egress_is_refused`, … |
| 4 other tenants | `ingress-isolation`: every pod selected, only own pods and the controller's namespace; `ospreyflow-public` no longer rendered behind the Ingress (it admitted every address) | `test_a_dropped_internal_policy_…`, `test_a_widened_ingress_policy_is_refused`, … |
| 5 renders unchanged | Every local-lite, small and cluster artefact byte for byte main's; the cluster's Helm text differs only in two comments and the quoted checksums; parsed, identical | `gates/p7_renders_unchanged.dd0233e1.log` (9bcadc6 vs dd0233e1) |
| 6 checksums | Quoted; test forces an all-digit digest (its first draft passed its plant: a 0-led digest PyYAML reads as text; fixed) | `test_helm_chart.py::test_a_checksum_of_digits_alone_is_still_text` |
| 7 Ingress | Timeouts 3600 s from the Glass's nginx, body size 512m from the Conduit's cap, each read from its source | `test_the_ingress_s_settings_follow_their_sources` |
| 8 fsGroupChangePolicy | `OnRootMismatch`; `fs-group-walk` rule | `test_a_volume_walk_at_every_start_is_refused` |
| 9 kind claims | Removed from §3c and Am 1 item 4, moved to P7a's list (Am 1 "Left"). LiteLLM as 10001: **proven** (the script's image refs were wrong; fixed). No-Java Conduit built: no java, no JAVA_HOME, no Java labels; imports and starts | `gates/p7_stores_uid_proof.2026-11-11.log`, `gates/p7_conduit_no_java.dd0233e1.log` |
| 10 Admin › Maps | Says there is no basemap route here yet; Am 1 "Left": none until P8 | `test_on_a_cloud_platform_the_build_says_there_is_no_basemap_route_yet` |
| 11 resources | Requests and memory limits on every container (proposals, unmeasured), ArcadeDB's heap ¾ of its limit; `no-resources` rule | `test_every_container_asks_…`, `test_arcadedb_s_heap_follows_its_memory_limit` |

**Rulings applied** (recorded in the friction row): the guide restored by name; `harness/cloud_platform/` extension points made data
(`profile.yaml`: doors, ours, group 0, always-hosts, resources); an image missing from `ours` refused in words.
**Minors, all fixed:** the duplicate parsers (`final_user` and one Helm runner, `tools/helm_chart.py`); `kind.yaml` a test fixture
(`OSPREY_PLATFORM_FOLDERS`); HANDOFF.md superseded; `render_values` refuses another profile in words; "an Enterprise" wording; the four
reds; the platform team's open questions in Am 1 "Left"; Terraform (no provider block, IRSA `:aud`, OpenSearch's security group and
policy); `values.yaml` declares the new keys. Egress from Admin's runtime settings stays L1.9's.

**`make test`'s four failures, none this branch's code:** `test_webapp_preflight::test_gpu_…` (this server has a working GPU);
`test_valkey_config::…_reached_plainly` (main's test never clears `VALKEY_PORT`, pinned to the offline 59993); two
`test_admin_guide` cases on `docs/administration-guide.md`, which is main's copy by the ruling, until `P7_admin_guide.diff` is applied.
At 4ee0625d `make test` also found two of mine (`gates/4ee0625d.test.txt`), fixed below the schemas commit: ADR-148 citing a process
ADR, and the Conduit's Debian upgrade moved out of its final stage.

**Decisions taken:** 9: the egress caps /16 and /48, for the reasons above. 10: the spec/10 appendix and generated type ride in the
schemas commit, as `PROFILE_NAMES` did (8), since they follow the schema's description. 11: `stack_lease.sh offline` cannot run on
the test server itself (it ssh'es to `ospreyflow-test`, which does not resolve here; there is no sshd), so each gate ran directly
with the ports it pins (59991–59994), no lane, no lease.

**Requests:** apply `P7_admin_guide.diff` and `P7_ci_makefile.diff` (its rule list updated) at merge and remake the guide's PDF;
mark ADR-148 Am 1's reservation row as written. **Report to glass:** `apps/workspace/nginx.conf.template` sets no
`client_max_body_size`, so nginx's 1 MiB default refuses a larger upload through the Glass on every profile, whatever the Ingress
allows. Main's carries stand: `create_investigation` sends no dataset; seeds default to `unit-1`; `render.py`'s
`_KEYCLOAK_DATABASE_SQL` lacks the PG16 GRANT for Small **and the cluster profile** on RDS.
