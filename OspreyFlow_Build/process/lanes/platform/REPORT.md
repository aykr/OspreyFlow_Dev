# Platform lane · P7 · report (10 November 2026, the `cloud-platform` profile, ADR-148) — NOT READY TO MERGE

P7 is in progress. The shared UID change merged alone (`fdd717d`, proofs in `gates/p7_uid_proof.7a89a87.log`).
The rest is on `lane/platform` above main `aec1f41`, with schemas at the head (the brief's rule, agreed by the
orchestrator). The lane-reviewer's 18 points are below, each marked fixed or open. `HANDOFF.md` says what the
next session does first. Nothing of this session is still running: the kind cluster is down, with 0 containers
and 0 images left on the test server.

## Exit criteria

| Criterion | State | Evidence |
| --- | --- | --- |
| `make cp-policy-check` green on the render | Met at `2e9afaa` (chart since changed; re-run) | `tools.cp_policy_check`: 0 violations, both fixtures; 67 passed on the server, with `test_helm_chart` and `test_cluster_render` |
| …red on each planted fault | **Partly**: reviewer point 2 | `tests/cp_policy_check/test_cp_policy_check.py`; no `P7_RED_RECORD.md` yet |
| ArcadeDB, ClickHouse, Keeper start as 10001 | Met, in Docker and on kind | `gates/p7_stores_uid_proof.2026-11-10.log`, `gates/p7_kind_check.677d473.log` |
| Acceptance scenarios on kind/k3d | **Not met** | The Conduit exits (no `OIDC_JWKS_URL`); the workspace image could not build (Docker Hub 429 on `node:22-slim`) |
| `local-lite`, `small`, `cluster` renders unchanged but the UIDs | Met for values and lock (the one intended difference is the `_Pins` fix) | `gates/p7_renders_unchanged.py` against main: 0 differences. The Helm output is untested (point 7) |
| A friction row | Written | `process/friction/2026-11-10-platform-p7-cloud-platform.md` (and the shared commit's row) |

On kind (`gates/p7_kind.sh`; Calico from quay.io, no ReadWriteMany class, an ingress controller):

- the stores are Ready as 10001 on `gp2-expand` ReadWriteOnce claims, with PDBs;
- the Calico deny and allow policies are applied: the internet is refused, the managed stand-ins and the namespace's pods are reached;
- the worker and ner run as 10001; the Conduit runs as 10001 with no Java;
- Keycloak builds itself and initialises its schema on the RDS stand-in, given group 0 as a supplementary group.

## Defects the cluster found, each fixed red-first

- **Calico policy names.** Calico 3.28+ stores a default-tier policy as `default.<name>`, so a Helm upgrade could not patch ours. They are now named with their tier.
- **The gateway's master key.** Our Secret dropped it while the Conduit still names it. The new test `test_every_key_a_pod_names_in_our_secret_is_in_it` covers this.
- **OpenSearch.** A pod named a secret for an OpenSearch address nothing reads, so it could not start. The variable is dropped; the domain stays in the Terraform.
- **Keycloak.** Its image is built for group 0, and it cannot build itself as 10001:10001.
- **`_Pins` double digests** (`ref@sha256:…@sha256:…`). Fixed in its own commit, with the pin test anchored at both ends.

## Decisions taken (for the owner to overrule)

1. **Shared folders before P8:** one ReadWriteOnce claim, its mounters co-scheduled on one node by pod affinity. Accepted by the orchestrator; a CARRIES row is on P8.
2. **Terraform:** plain AWS/Kubernetes resources in the environments repository's shape, not the platform's modules, whose sources would name the client in this repository.
3. **Egress by networks:** Calico's open-source policy matches networks, not names, so every enabled host names its networks in `cloud_platform.egress_nets`. One without is refused at render.
4. **No baked docker group in the harness image:** run with `--group-add` instead.
5. **No pod is given an OpenSearch address** until the index leg reads one.
6. **Keycloak gets supplementary group 0** on this profile, not a thin image (it leaves in P10).
7. **Java via a build argument** (`CONDUIT_JAVA=omitted`), not a second Dockerfile (ADR-148 question 3, the recommended answer).

## The reviewer's 18 points

- **Open: the exit evidence and red record (1, 2).**
  - 1: the exit evidence. Partly answered by the logs now in `gates/`; the acceptance run is still open.
  - 2: `P7_RED_RECORD.md`, with each policy-check branch red on its own fault: `allowPrivilegeEscalation`, the capabilities, a container port and a Service port separately, and a StatefulSet's RWX claim template.
- **Disputed (3):** schemas at the branch head, per the brief.
- **Open: egress (4).** Mail, organisation sign-in and connector hosts are missing, and `OSPREY_CONNECTOR_EGRESS` has no route in. The client's S3 gateway endpoint is a prefix list, not the VPC CIDR, and IRSA's STS call needs a route too. The list is read from `osprey.yaml`, not from Admin's runtime settings (L1.9).
- **Open: the Ingress (5).** It lacks Caddy's `id.<host>/assets/govuk` route, and has no TLS secret setting; the `id.`/`bi.` hosts sit two levels below the platform's wildcard.
- **Open: unproven images (6).**
  - LiteLLM and the postgres init containers are not shown starting as 10001 with every capability dropped.
  - The stores' proof lacks `--cap-drop ALL` and `no-new-privileges`.
  - Keycloak is now shown on kind.
- **Open: ownership and the chart's output (7).**
  - The chart templates outside `ingress.yaml` are edited; that needs the orchestrator's acceptance.
  - No test holds the cluster's Helm output unchanged (`p7_renders_unchanged.py --helm` was promised and not built).
  - The rendered pods' shared-claim affinity is untested.
- **Open: `images push` (8).** No fake registry models a refusal. The by-digest copy never ran against a real registry. There is no `--platform` (an arm64 Mac would push arm64).
- **Open: the stand-ins (9).** The kind stand-ins are more permissive than RDS: a superuser, and TLS not forced. The kind S3-key and CA patches bypass the rendered IRSA and TLS paths, and `report-sync` is unpatched.
- **Open: tests (10, 11).**
  - 10: the image-pin test is end-anchored.
  - 11: the readers test leaves out init containers, Keycloak and LiteLLM, and the Amendment's "no other" is untrue for them. `READERS`/IRSA name `ingest`, which this profile never renders.
- **Open: minors (12–18).**
  - 12: the Java-less build is never built in a test, and its image keeps the Java labels.
  - 13: Calico's CRDs are not schema-checked.
  - 14: spec/05 is silent on the profile, and the reservation row still says reserved.
  - 15: duplications (`OURS`, `in_kind_registry`, `_egress_hosts`, `_refuse`).
  - 16: renderer edges (`plan.setdefault`, an empty `:sha256-` tag, any non-zero UID accepted, global bucket names).
  - 17: wording.
  - 18: `tofu init` in the check needs the network.
- **New, from the cluster:** the Conduit and the workers need the non-secret settings `harness.apply` writes for a cluster (`OIDC_JWKS_URL`, the issuer, …). This profile renders none of them; they belong in its ConfigMap.

## Commits (main..HEAD)

`65091cd` harness · `be0639a` chart · `0a925d2` policy check · `8dc5084` images push · `12017bd` Java arg and
Maps' words · `e3950ff` render comparison · `0001f7b` `_Pins` fix · `0c1ec85` stores proof · `0c88235` OpenSearch,
kind file, format · `0d36f5b` ADR-148 Am 1 and kind scripts · `f572a88` schemas · `79e3d0c` Calico names ·
`2f21d20` gateway key · `677d473` Keycloak group. The next session moves the schemas commit back to the head.

## Requests to the orchestrator

- Accept, or reassign, the chart template edits beyond `ingress.yaml`.
- Apply `P7_ci_makefile.diff` once the red record is in.
- The reservation row for ADR-148 Am 1 to say written, at merge.

## Gates

`make -k ci` and `make test` have not been run for P7: they wait for the open points.
