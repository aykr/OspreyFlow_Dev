# Draft, for `spec/06_DECISIONS.md` once the orchestrator reserves a number (rule 11)

Written on the test server, 11 November 2026, with the orchestrator offline: no amendment number could be
reserved, so this waits here rather than going into an accepted ADR's place. Proposed heading:

### ADR-135, Amendment <n> (11 November 2026) — Amendment 4's two engine kinds as built in *Admin › Models* (P11 part 1): the client's own gateway by its token and Bedrock in London by the IAM role, no key stored for an IAM-role engine

Status: as built by the platform-b lane (P11 part 1), after its own lane reviewer's round, for the
orchestrator's review. Amendment 4 is unchanged except where this settles it.

1. **An engine's kind and its sign-in are settings of the engine** (`ModelProviderConfig`): `kind` is
   `provider` (as before), `gateway` (the client's own OpenAI-compatible AI gateway, its `api_base` required,
   reached through LiteLLM's `openai/` route) or `bedrock` (LiteLLM's `bedrock/` route, no `api_base`);
   `auth` is `key` (a key, or a gateway's token, by Amendment 2's write-only path) or `iam_role`; `region` is
   Bedrock's alone and only `eu-west-2`, its default. Refused in words, naming the field and never the value:
   Bedrock by a key; any region but London; a region on another kind; a gateway with no address; a provider
   by the role; **an engine named `bedrock` of any other kind** (LiteLLM routes a provider by its name, so it
   would reach Bedrock by a stored key in no fixed region); and **the client's gateway by the role** (held,
   point 5). The gateway entry's `model_name` stays `<engine>/<model>`.
2. **An engine's kind is fixed once added** (Amendment 2 decision 1: "the provider's name (fixed once
   added)"). Another kind is another processor, which the engine's contract mark (ADR-136) and label do not
   cover; it is removed and added again.
3. **No key is stored for an IAM-role engine**, anywhere: its gateway entries name no credential and carry no
   key of any kind (Bedrock's carry `aws_region_name: eu-west-2` alone; the gateway pod's own identity signs);
   the models file holds no key record; its key state is `iam_role` ("IAM role: no key kept"); `PUT` and
   `DELETE …/key` are refused (409) and audited; `ospreyflow models` lists it as keeping none, and `models
   key`/`remove-key` refuse it before any key is read; `move` skips and names a key line for it; the install
   asks for none and its page offers no key field. **A key held under its name from before**
   (`OSPREY_MODEL_KEY_<NAME>` in `deployment.env` or the cluster's Secret) is blanked in every service and
   workload, the gateway too. It is offered to analysts with no key; declared in `osprey.yaml`, its gateway
   entries and its own gateway key are made at the Conduit's start, with no models file (it has no key to
   move in, which is what made a keyed engine's entries).
4. **Changing how an engine signs in, or its region, removes its key**, as a change of address does
   (Amendment 2 decision 1, the owner's ruling). As built no edit reaches this beyond the address (the kind is
   fixed and each kind has one sign-in); it stays as the guard. The credential's removal is written to the
   models file at once, so a reconcile refused after it says "no key", never "key set".
5. **The client's gateway by the IAM role is refused for now** (held for the owner, Q1 of the platform-b
   server log; the strict option, on the lane reviewer's finding): LiteLLM's OpenAI client sends no request
   without a key, so such an engine would be offered to analysts and fail every call. *Models* says the
   gateway signs in by a token for now. How a client's gateway takes the namespace's identity (AWS SigV4, or
   the pod's web-identity token as a bearer) is the client's to say; nothing here guesses.
6. ***Test the connection*** reads Bedrock's refusals: botocore's "Unable to locate credentials", STS
   refusing `AssumeRoleWithWebIdentity` and a 403 as the key refused; its 400 `ValidationException` and
   "on-demand throughput isn't supported" (an inference profile's id is the model to name) as the model not
   offered; `ThrottlingException` as a rate limit. For Bedrock it says in words of the role, not of a key,
   what to check.

**Fixtures (rule 15).** The stand-in gateway's client gateway and Bedrock are **recorded, not measured**: no
client gateway and no AWS account is reachable from the build. Each refusal is modelled from the
OpenAI-compatible and AWS/botocore documented answers and shown by
`tests/adapters/model_litellm/test_stand_in_engine_kinds.py` before any test trusts it; the stand-in's own
docstring says which of its behaviours were measured and which recorded. The classifier's Bedrock strings
match words the stand-in itself writes, so they are only as right as the recording: **a measurement against
the real Bedrock in London is part 2's**, and changes this record where it differs.

**Tests** (`process/lanes/platform-b/p11/RED_RECORD.md`, each red first and each fault planted at its call
site): `tests/services/api/test_model_engine_kinds.py` (the schema's refusals; rule 4 on every Models route
for each kind; a planted token in no response, log, audit, file or gateway row; no key stored for an
IAM-role engine, its removal refused and nothing carried to Bedrock with the call; Bedrock signed by the
pod's role in London; the kind fixed once added; "no key" after a refused reconcile; a declared IAM-role
engine's entries made at start; the command line moving no key for it; each kind's limits on its own
gateway key; the render, routing, install and install page for an engine declared in `osprey.yaml`; a held
key blanked in every compose service and cluster workload); `tests/cli/test_models_verb_iam_role.py`;
`Models.test.tsx`; `keyboard/admin-models.spec.ts` (two cases, rule 13); axe on two new *Models* states in
the three themes.

**Cost.** P2's limits are shown applied to each kind's own gateway key, not enforced on a call to either
kind (the stand-in enforces limits by key whatever the upstream, so this was not exercised end to end).
