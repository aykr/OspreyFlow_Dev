# Draft, for `spec/06_DECISIONS.md` at merge (rule 11): ADR-135 Amendment 8, reserved for platform-b (35cffcd)

Written on the Mac, 11 November 2026, on `lane/platform-b-p11p2`, after the orchestrator's and my own reviews of
round 1 (ee6e524).

### ADR-135, Amendment 8 (11 November 2026) — The model route wired into the cloud-platform profile (P11 part 2): the gateway rendered by default, its own IAM identity for Bedrock alone, and an engine enabled only where the render made its way out

Status: as built by the platform-b lane (P11 part 2), on the orchestrator's rulings of 11 November (MORNING 37,
option A, least privilege; and round 1's ruling on engines added in *Admin › Models*), recorded for the owner.
Amendment 7 is unchanged except where this settles it: its decision 7's "until part 2, a Bedrock engine on
cloud-platform has no credentials" is closed **for a Bedrock engine declared in `osprey.yaml`** (decision 2);
one first added in *Admin › Models* is refused (decision 4).

1. **The gateway's pod is rendered by default on `cloud-platform`**, with or without an engine enabled at install.
   That is the pod alone: an engine first added in *Admin › Models* still has no way out of the namespace, and for
   Bedrock no identity, until it is declared, the deployment re-rendered and the platform's Terraform applied
   (decision 4). With no Bedrock engine the gateway runs as the namespace's `default` service account, under no
   role.
2. **The gateway's own IAM identity, for Bedrock alone, made only while a Bedrock engine is declared**: a service
   account of its own (`secrets.irsa.gateway_service_account`; `ospreyflow-gateway` on the client's platform), which
   `litellm` runs as; and an IAM role (`terraform/gateway.tf`) granting `bedrock:InvokeModel` and
   `bedrock:InvokeModelWithResponseStream` on `arn:aws:bedrock:eu-west-2::foundation-model/*` (each Bedrock
   engine's region, London alone by Amendment 4), so IAM itself holds the region; **no S3 action and no other
   service**; its trust one statement, the cluster's OIDC provider alone, `StringEquals` on `:sub` (that one
   account) and `:aud` (STS). Never the namespace's account, whose role holds the buckets and is unchanged. The two
   account names are Kubernetes names and differ; a platform naming no gateway account is refused in words when a
   Bedrock engine is declared.
3. **The namespace reaches an engine's host only while that engine is declared at render**: with no engine, the
   egress is the profile's `always` hosts alone (S3 and STS); each declared engine adds its own host (its address,
   its kind's row, or its provider's). An engine disabled in *Admin › Models* keeps its host open until the next
   render. The gateway shares the namespace's egress: the Calico policy selects every pod (`all()`), so the hosts
   are the namespace's, not the gateway's alone.
4. **Admin › Models enables an engine only where the render made it** (the orchestrator's ruling): the render
   tells the Conduit what it made (`OSPREY_MODEL_ROUTES_MADE`: the engine hosts, the rules that place an engine's
   host, whether the gateway's own role exists), and on `cloud-platform` an engine whose host is not among them,
   or a Bedrock engine without the role, is refused before the gateway is asked: "On this deployment an engine is
   reached only once the render has made its way out of the namespace (and, for Bedrock, the gateway's own IAM
   role), and it made none for this engine. Declare it in osprey.yaml, re-render, and have the platform team apply
   the Terraform; then it can be enabled here." Never a silent failure. **The same holds wherever an engine comes
   from the models file** (a restore, or a render that dropped one): such an engine is never written into the
   gateway (its stale entries are deleted), never offered to analysts, refused a key or limits, and marked in
   *Admin › Models* "not made by the render: <those words>". With no word from the render on `cloud-platform`,
   nothing is made (fails closed). Every other profile reaches any host, as before.
5. **The words name the gateway's own IAM role**, not the namespace's: *Admin › Models*, its connection test's
   words (`key_refused` sends the platform team to `terraform/gateway.tf`, not the bucket role), the command line,
   the schema's descriptions and the administration guide's appendix (`p11p2/docs-admin-guide-P11p2.diff`).
6. **A contract reference's word-by-word key check is `cloud-platform`'s alone** (the orchestrator's ruling):
   every other profile reads a reference exactly as before (Amendment 7 decision 1), a long reference number
   among words included.

**Tests** (`p11p2/RED_RECORD.md`; the W plants in `p11/plant.py`): `tests/harness/test_cloud_platform_gateway.py`
(the gateway by default, no host without an engine, the gateway's account only with Bedrock, the role's two
documents compared block by block and that comparison shown red by eighteen planted shapes, no other Terraform
file naming the gateway's role, policy or account (three planted strays), the namespace's role
unchanged, the accounts kept apart, the refusal without one), P7's two cases changed in
`test_cloud_platform_render.py`, `test_rendered_terraform.py`'s `production-bedrock` shape (OpenTofu's fmt, init and
validate on `gateway.tf`; with cp-policy-check, on the new `production-bedrock` fixture), and
`tests/services/api/test_model_engine_kinds.py` (the stand-in's environment and role from the real render of what
`osprey.yaml` declared, rule 15; the refusal of an engine the render did not make, seven shapes and a moved
address; the reference off cloud-platform).

**Ownership.** `harness/cloud_platform/**`, the platform's settings model and P7's fixtures are platform's (ADR-142
Amendment 8 decision 3): `p11p2/cloud-platform-P11p2.diff`, applied at merge. The guide's appendix is the docs
lane's: `p11p2/docs-admin-guide-P11p2.diff`, with its version row and PDF at merge.

**Not done, recorded.** Checked as rendered, not against AWS (no AWS account is reachable from the build): whether a
real namespace's role signs a real Bedrock call in London is the post-deployment check's. The gateway's account
carries no `eks.amazonaws.com/sts-regional-endpoints` annotation and only `sts.eu-west-2` is allowed out; whether
LiteLLM's botocore uses the regional endpoint by default is unmeasured. A model's first use may need
`aws-marketplace` actions, or an administrator enabling it in Bedrock's Model access, first; newer Claude models in
eu-west-2 are offered only through inference profiles, which Amendment 7 decision 2 refuses. IAM role names are
account-wide (as `irsa.tf`'s are). On cloud-platform a reference holding one long mixed word
(`CCS-RM6098-ACME-2026-000123`) is refused; write it with spaces. A UUID-shaped token, and a key split across
path segments, are taken in an address's path. CARRIES' P11 minors stay carried: Bedrock's `model_not_enabled`
words key on a string AWS does not document; the other-shape gateway test accepts either refusal; the stand-in never
cools an entry after a 429 and LiteLLM's cooldown is unmeasured.
