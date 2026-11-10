# Platform · P7 handoff (10 November 2026)

**Step:** P7, the `cloud-platform` profile (`BRIEF_P7.md`, ADR-148, Amendment 1 on the branch). The shared UID
commit is merged (`fdd717d`); the rest is on `lane/platform` above main `aec1f41`. **Last commit:** this file's.
**Running:** nothing. The kind cluster is down (0 osprey-p7 containers or images on ospreyflow-test).

**Done:**
- The renderer (values, the push plan, Terraform), the chart's Ingress and gated blocks, Calico deny and allow.
- `cp-policy-check` (green on the server at `2e9afaa`), `ospreyflow images push`, `CONDUIT_JAVA=omitted` and the Maps words.
- The `_Pins` fix; renders unchanged against main.
- The stores as 10001 (Docker and kind); kind with Calico, no RWX class, egress refused and allowed as rendered.
- Five defects the cluster found, fixed red-first.

**Next, in order:**
1. Render the cluster's non-secret settings (`OIDC_JWKS_URL`, the issuer and the rest `harness.apply` writes for a
   cluster) into this profile's ConfigMap; the Conduit and the workers exit without them. Test first.
2. `P7_RED_RECORD.md`: each `cp_policy_check` branch red on its own fault (REPORT point 2), and `images push`
   against a fake that refuses as a registry does (point 8); add `--platform linux/amd64`.
3. Egress (point 4): mail, organisation sign-in, connector hosts; S3 and STS by the platform's prefix list or
   endpoint settings, not the VPC CIDR.
4. Ingress (point 5): the GOV.UK assets route from `harness/site.py`, a TLS secret setting.
5. Points 6, 7, 9–11: LiteLLM and the postgres init containers as 10001 with capabilities dropped; a Helm-output
   comparison for the cluster (`p7_renders_unchanged.py --helm`); the readers test widened; the pin test anchored.
6. Then kind again: `p7_kind.sh up`, `deploy`, `check`, then the acceptance scenarios over the wire
   (`test_phase8_exit_over_the_wire.py`, port-forwarded, after a seed). Docker Hub's 429 blocks the workspace's
   `node:22-slim`: use the orchestrator's new Hub mirror on the server. Tell the orchestrator up/down; 8 GB cap.
7. Move the schemas commit back to the head; run the lane-reviewer; `make -k ci` and `make test` (granted).

**Open questions:** the chart templates beyond `ingress.yaml` need the orchestrator's acceptance (asked).

**Do not redo:** the UID proofs (merged); the Calico tier naming; the gateway-key and OpenSearch fixes; the
Keycloak group-0 measurement (`gates/p7_kind_check.677d473.log`).
