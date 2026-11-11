# Platform-b · brief P11 part 2 · the model route wired into the cloud-platform profile

Written by the orchestrator, 11 November 2026, after P11 part 1 merged (2733de4). Binds: `process/CLAUDE.md` rules 1–15,
`process/lanes/PROMPT_L.md`, ADR-142 Amendments 6–8, ADR-135 Amendments 4 and 7, ADR-148 and its Amendments 1 and 5.
A credential step: two review rounds, listed for the owner.

**What (BUILD_PLAN_PARALLEL_LANES.md, "Two tracks", P11 part 2).**
1. **The gateway rendered by default** on `cloud-platform`, so an engine first added in *Admin › Models* has a gateway
   without a re-render.
2. **The gateway's own IAM identity** (the orchestrator's ruling, MORNING 37: option A, least privilege):
   - a service account and an IAM role of the gateway's own, made only when a Bedrock engine is enabled;
   - the role grants `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on
     `arn:aws:bedrock:eu-west-2::foundation-model/*` only: no S3 action, no other region;
   - its trust is bound to that service account alone, through the cluster's OIDC provider;
   - `litellm` runs as it, and P7's service-account test changes to expect it on `litellm` when Bedrock is enabled;
   - the second account name goes in `PlatformSettings.secrets`, which is platform's schema, so send it as a diff.
3. **The model host allowed out only while an engine is enabled** (already true; prove it on the render with the
   gateway on by default).

**Carried in from part 1** (CARRIES, P11 rows): `contract_reference`'s per-word key check; round 2's plants into
`p11/plant.py` with raw output; the gateway-role probe switched to BEDROCK so the four strict xfails XPASS when the
identity lands; the minors.

**Ownership (Amendment 8 decision 3).** Your template file(s) are yours. `values.yaml`, the profile's settings model,
`render.py`'s profile entry, `harness/cloud_platform/**`, `_helpers.tpl` and `storage.yaml` are platform's: send
diffs. P7b renders what you leave.

**Exit.**
- The four strict xfails (NO_GATEWAY_IDENTITY) pass and are made plain tests.
- A test that the gateway role's policy holds no S3 action and no region but eu-west-2, red first.
- cp-policy-check green on all three shapes with the gateway on.
- The stand-in gives the gateway only the identity the render gives it (rule 15).
- Gates once through `stack_lease.sh offline platform-b`.
- The test server is quiet from 12:00 UK time on Friday 13 November until the owner's demo is over.
