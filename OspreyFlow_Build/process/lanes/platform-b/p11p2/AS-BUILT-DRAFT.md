# Draft, for `spec/06_DECISIONS.md` at merge (rule 11): an ADR-135 amendment for P11 part 2, number to be reserved

Written on the Mac, 11 November 2026, on `lane/platform-b-p11p2` from main 1d97ea9. Proposed heading:

### ADR-135, Amendment <n> (11 November 2026) — The model route wired into the cloud-platform profile (P11 part 2): the gateway rendered by default, its own IAM identity for Bedrock alone, the model host allowed out only while an engine is enabled

Status: as built by the platform-b lane (P11 part 2), on the orchestrator's ruling of 11 November (MORNING 37,
option A, least privilege, recorded for the owner). Amendment 7 is unchanged except where this settles it: its
decision 7's "until part 2, a Bedrock engine on cloud-platform has no credentials" is closed by decision 2.

1. **The gateway is rendered by default on `cloud-platform`**, with or without an engine enabled at install, so an
   engine first added in *Admin › Models* has a gateway without a re-render (P7 rendered it only with an engine).
2. **The gateway's own IAM identity, for Bedrock alone, made only while a Bedrock engine is enabled**: a service
   account of its own (`secrets.irsa.gateway_service_account` in the platform's settings, `ospreyflow-gateway` on the
   client's), which `litellm` runs as; and an IAM role (`terraform/gateway.tf`) granting `bedrock:InvokeModel` and
   `bedrock:InvokeModelWithResponseStream` on `arn:aws:bedrock:<region>::foundation-model/*` for each Bedrock
   engine's region (London alone, by Amendment 4), so IAM itself holds the region; **no S3 action and no other
   service**, the buckets staying the namespace's own account's; its trust bound to that one account through the
   cluster's OIDC provider, for STS alone. Never the namespace's account, whose role holds the buckets. With no
   Bedrock engine, no gateway account or role is made, and `litellm` runs under none. A platform whose settings name
   no gateway account is refused in words when a Bedrock engine is enabled.
3. **The namespace reaches a model host only while an engine is enabled**: with the gateway running and no engine,
   the egress is the profile's `always` hosts alone (S3 and STS); each enabled engine adds its own host (its address,
   its kind's row, or its provider's).

**Tests** (`p11p2/RED_RECORD.md`, each red first, and the W plants in `p11/plant.py`):
`tests/harness/test_cloud_platform_gateway.py` (the gateway by default, no model host without an engine, the
gateway's account only with Bedrock, the role's policy checked and that check shown red with each fault planted: an S3
action, another region, any resource, any action, the namespace's account, no OIDC), P7's two cases changed in
`tests/harness/test_cloud_platform_render.py`, and `tests/services/api/test_model_engine_kinds.py`'s four cases that
need the identity, plain tests again, the stand-in's gateway given a role only as the render gives one (rule 15).

**Ownership.** `harness/cloud_platform/**` and the platform's settings model are platform's (ADR-142 Amendment 8
decision 3): the change is `p11p2/cloud-platform-P11p2.diff`, with P7's `kind` test fixture, applied at merge.

**Not done, recorded.** The role's grant is checked as rendered, not against AWS: no AWS account is reachable from
the build, so whether a real namespace's role signs a real Bedrock call in London is the post-deployment check's.
CARRIES' P11 minors stay carried: Bedrock's `model_not_enabled` words key on a string AWS does not document; the
other-shape gateway test accepts either refusal; the stand-in never cools an entry after a 429 and LiteLLM's cooldown
is unmeasured; a UUID-shaped token in an address's path is taken (a resource id there is ordinary).
