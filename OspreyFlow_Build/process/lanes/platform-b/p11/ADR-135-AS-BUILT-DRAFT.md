# Draft, for `spec/06_DECISIONS.md` at merge (rule 11): ADR-135 Amendment 7, reserved for platform-b

Written on the test server and finished on the Mac after the rebase onto P7 (main 5a554e3), 11 November 2026. The
number is the orchestrator's reservation (main 354bbec). It stays here, in `p11/`, until the branch merges.

### ADR-135, Amendment 7 (11 November 2026) — Amendment 4 as built in *Admin › Models* (P11 part 1): on the `cloud-platform` profile alone, the client's own gateway at its address by a token and Bedrock in London by the IAM role and a model's own id, no key stored for an IAM-role engine

Status: as built by the platform-b lane (P11 part 1), after its own lane reviewer's round and the orchestrator's
review rounds 1 and 2 (11 November), whose rulings decisions 1, 2, 3 and 7 record. Amendment 4 is unchanged except where this
settles it. Decision 2's ruling is recorded **for the owner to overrule**.

1. **Amendment 4's engine kinds and their rules are the `cloud-platform` profile's alone** (the orchestrator's
   ruling, conformance with Amendment 4, which is scoped to that profile, and with decision 1, which keeps `bedrock`
   and `azure` working through the same shape everywhere else). On every other profile an engine is a provider by
   its name and key **exactly as before Amendment 4**: an engine named `bedrock` is LiteLLM's Bedrock provider by its
   key there, as it always was; the two kinds, signing in by the IAM role and a region are refused in words naming
   the profile; *Admin › Models* offers neither kind (the view's `engine_kinds` is `provider` alone, and `bedrock`
   stays in its list of providers); and the models file, the Conduit's `OSPREY_MODEL_ENGINES` line and the audit do
   not name the new fields for a plain provider, so they are written as before. One function decides
   (`schemas.deployment.engine_refusal(engine, profile)`), and **every reader of an engine calls it with the
   deployment's profile**: `osprey.yaml` (`OspreyConfig`), the Conduit's start (`Installed.from_env`), the models file
   (`ModelSettingsFile.load`) and each change in *Admin › Models* (`ModelAdmin._validated`). The Conduit reads its
   profile from `OSPREY_PROFILE`, which the render writes into `deployment.env` for every profile, and the
   `cloud-platform` render (P7) into the Conduit's environment as `cloud-platform` (held by
   `test_the_cloud_platform_render_tells_the_conduit_its_profile`, red with that line planted out). On `cloud-platform`, the rules as before:
   - `kind` is `provider`, `gateway` (the client's own OpenAI-compatible AI gateway, its `api_base` required, through
     LiteLLM's `openai/` route) or `bedrock` (LiteLLM's `bedrock/` route, no `api_base`); `auth` is `key` (a key, or
     the gateway's token, by Amendment 2's write-only path) or `iam_role`; `region` is Bedrock's alone and only
     `eu-west-2`, its default;
   - refused in words, naming the field and never the value: Bedrock by a key; any region but London; a region on
     another kind; a gateway with no address; a provider by the role; an engine named `bedrock` of any other kind
     (LiteLLM routes a provider by its name, so it would reach Bedrock by a stored key in no fixed region); the
     client's gateway by the role (held, decision 6); and decisions 2 and 3.
   The gateway entry's `model_name` stays `<engine>/<model>`. **On the real profile since the rebase onto P7**: the
   harness's cases, first run on a widened profile set, are on P7's own `cloud-platform` fixture, and moving them
   found the render refusing the very engines it rendered twice over. P7's render validates the deployment's cluster
   translation as `profile: cluster`, where these kinds are refused: the translation is now validated with
   `ENGINES_AS` in its context, so its engines stay held to cloud-platform's rules. And P7's egress took an engine's
   host from its address or its provider's name: a Bedrock engine names neither, and its host is now its region's
   runtime (`bedrock-runtime.eu-west-2.amazonaws.com`), allowed by its networks like any other, or refused in words.
   The render writes `OSPREY_PROFILE=cloud-platform`, by which the Conduit offers and takes the kinds. A
   cloud-platform render runs the gateway only with an engine enabled at install (P7), so an engine first added in
   *Admin › Models* there has no gateway until the deployment is rendered again with it.
2. **London only covers the model's id** (the orchestrator's ruling, from Amendment 4's "Bedrock in the client's
   London region"; for the owner to overrule). A Bedrock model is named by its own id (`anthropic.…`). A
   cross-region inference profile's id puts a geography before it (`eu.…`, `us.…`, `apac.…`, `global.…`, and others
   such as `us-gov.…`, `jp.…`) and may send the call outside London; an ARN may name another region or an
   application inference profile wrapping one. AWS's own guide to cross-region inference says not to rely on the
   prefix alone to tell where a call may go, so **any id with a part before the provider's, and any ARN, is
   refused**, in fixed words, rather than a list of known prefixes. A model Bedrock offers in London only through an
   inference profile ("on-demand throughput isn't supported") is therefore not usable here; *Test the connection*
   says so in words (decision 5), and points at a model offered on demand in London, never at an inference profile.
3. **No key in the gateway's address, label or reference.** On `cloud-platform` an engine's `api_base` with userinfo
   (`https://<key>@host/…`, `https://user:<key>@host/…`), a query or fragment (`?api-key=…`, `#…`), or a path segment
   shaped like a key (`https://host/v1/<token>`: a key prefix, a JWT, or 24 or more characters mixing upper case,
   lower case and digits; a deployment's lower-case name such as `my-deployment-2024-08-06` is taken) is refused, and
   so is a label shaped like a key (the contract reference already was, on every profile, by ADR-136). **A JWT**
   (`eyJ….…`, the shape most gateways issue tokens in, padded, encrypted as a JWE or with its dots percent-encoded)
   is a key's shape in the label and the reference, which the unbroken-run check missed for its dots; **the
   reference's check is every profile's** (ADR-136), so a reference holding a JWT is now refused on Lite, Small and
   cluster too, and a models file holding one fails at the Conduit's start. On `cloud-platform` a label is also
   checked word by word, so a token among words is refused. A path segment of 24 or more unhyphenated lower-case
   letters and digits (a hex subscription key) is refused; a deployment's name of 24 or more characters mixing
   case and digits (`GPT4oMiniProdDeployment2024`) is refused too, a false refusal its operator renames past. **The
   refusals never quote the value in *Admin › Models***; the set-up console (`harness/webapp.py`'s 422, which returns
   pydantic's errors with their input) and `str(ValidationError)` on the command line still show it, which is the
   console's and the command's own (not this step's files), carried. A key pasted
   there would be kept in the models file, the gateway's entries and the audit, and shown in *Admin › Models*. Held to
   `cloud-platform` by decision 1's ruling; **recommended for the owner**: the same refusals on every profile, which
   would change how other profiles take an address (a separate decision).
4. **An engine's kind is fixed once added** (Amendment 2 decision 1: "the provider's name (fixed once added)").
   Another kind is another processor, which the engine's contract mark (ADR-136) and label do not cover; it is
   removed and added again. **Only the address decides where a key goes**: each kind has one sign-in and Bedrock one
   region, so the guard that removed a key when the sign-in or region changed was unreachable and is removed. When
   the client's gateway by the role is admitted (decision 6), a change of sign-in becomes reachable, and the guard
   returns with its test.
5. ***Test the connection*'s refusals**, each with its own words (`adapters/model_litellm/connection.py`,
   `ModelAdmin.KIND_WORDS`):
   - Bedrock: no identity on the gateway's pod (botocore's "Unable to locate credentials"), STS refusing
     `AssumeRoleWithWebIdentity`, and a 403 naming the role, as the role refused (`key_refused`, said in words of the
     role); a 403 `AccessDeniedException` "You don't have access to the model with the specified model ID" as **the
     model's access, not the role's permissions** (`model_not_enabled`); a 403 `ExpiredTokenException` as the role's
     credentials expired (`sign_in_expired`); a 400 "The provided model identifier is invalid" or "on-demand
     throughput isn't supported" as the model not offered on demand in London (`model_not_offered`); a 429 as a rate
     limit.
   - The client's gateway: a 401 or 403 as its token **or its own policy** (the status cannot tell them apart, so the
     words name both); a 404 as the model not offered to the token; a 429 as its own limit; and a 4xx in a shape that
     is not OpenAI's (an API manager's fault, a firewall's HTML page), which the classifier reads as nothing it
     knows, as **refused** (`request_refused`, given by *Admin › Models* for this kind alone, so no other provider's
     answers read differently), never as unreachable.
   - **Where Bedrock's words come from.** The classifier matches the message text LiteLLM passes through, never the
     header carrying the exception's name. Checked against AWS's public documentation on 11 November 2026:
     | Words matched | Source |
     | --- | --- |
     | "The security token included in the request **is** expired" (`ExpiredTokenException`, 403) | Documented in AWS's Bedrock error reference (<https://docs.aws.amazon.com/bedrock/latest/APIReference/CommonErrors.html>) as "…**has** expired. Request a new security token and try again." The classifier reads both. |
     | 429 (`ThrottlingException`) | Documented (<https://docs.aws.amazon.com/bedrock/latest/userguide/troubleshooting-api-error-codes.html>); the classifier reads the status alone, not the words. |
     | 403 naming the role, "is not authorized to perform: bedrock:InvokeModel" | The documented `AccessDeniedException` is generic (CommonErrors above); the classifier reads the status alone. |
     | "You don't have access to the model with the specified model ID." | **Not found in AWS's documentation** (the troubleshooting page names model-access causes in other words). Recorded from what Bedrock is widely reported to answer, not documented, not measured. |
     | "The provided model identifier is invalid." | **Not found in AWS's documentation.** Recorded, not measured. |
     | "…with on-demand throughput isn't supported…" | **Not found in AWS's documentation.** Recorded, not measured. |
     | "Unable to locate credentials" | botocore's `NoCredentialsError` (`botocore/exceptions.py`); not re-read this session. |
     | "AssumeRoleWithWebIdentity" | The STS operation's own name; the EKS IRSA troubleshooting page could not be read this session. |
     **None of these has been measured against the real Bedrock in London**: that is part 2's (Q5), and changes this
     record where it differs. The stand-in's words were written to match these, not the other way round.
6. **The client's gateway by the IAM role is refused for now** (held for the owner, Q1 of the platform-b server log):
   LiteLLM's OpenAI client sends no request without a key, so such an engine would be offered to analysts and fail
   every call. How a client's gateway takes the namespace's identity (AWS SigV4, or the pod's web-identity token as a
   bearer) is the client's to say; nothing here guesses.
7. **No key is stored for an IAM-role engine**, anywhere: its gateway entries name no credential and carry no key of
   any kind (Bedrock's carry `aws_region_name: eu-west-2` alone); the models
   file holds no key record; its key state is `iam_role` ("IAM role: no key kept"); `PUT` and `DELETE …/key` are
   refused (409) and audited; `ospreyflow models` lists it as keeping none, and `models key`/`remove-key` refuse it
   before any key is read — **also when the Conduit does not answer**, for an engine `osprey.yaml` declares so and
   for any engine on `cloud-platform` (one added in *Admin › Models* is not in `osprey.yaml`); every other profile is
   asked for a key as before. `move` skips and names a key line for it; the install asks for none and its page offers
   no key field. A key held under its name (an earlier engine of that name) is blanked in every workload of the
   cluster's translation, which the `cloud-platform` render reuses, the gateway too. **The gateway's workload carries
   no static AWS key** (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`), which botocore would prefer
   to the pod's identity, whether Bedrock is declared at install or added later. Declared in `osprey.yaml`, an
   IAM-role engine's gateway entries and its own gateway key are made at the Conduit's start, with no models file,
   with every other declared engine's (a keyed one's name its credential and answer once its key moves in).
   **Who signs Bedrock's calls is P11 part 2's** (the orchestrator's ruling on round 2, recorded for the owner): the
   gateway's pod must hold an IAM identity of its own, and **the cloud-platform render gives it none today** (the
   namespace's IRSA account is the Conduit's, the workers' and the report sync's, and its role grants S3 alone). So
   **until part 2, a Bedrock engine on `cloud-platform` has no credentials**, and *Test the connection* says so.
   Part 2 renders, least privilege, only while a Bedrock engine is enabled: a separate gateway service account and
   IAM role, trusted through the cluster's OIDC provider by that account alone, granting `bedrock:InvokeModel` and
   `bedrock:InvokeModelWithResponseStream` on `arn:aws:bedrock:eu-west-2::foundation-model/*` and nothing else (no
   S3, no other region, which IAM then enforces). The stand-in's gateway holds a role only as the real render gives
   one, so the four cases that need the identity are strict expected failures named for part 2.

**Fixtures (rule 15).** The stand-in gateway's client gateway and Bedrock are **recorded, not measured**: no client
gateway and no AWS account is reachable from the build. Each refusal is shown by
`tests/adapters/model_litellm/test_stand_in_engine_kinds.py` before any test trusts it: the client gateway's no
token, wrong token, model not offered, policy 403, own 429, a refusal in another shape, and its address with or
without a trailing slash; Bedrock's no identity, role not trusted, role not allowed, credentials expired, model not
granted, model not offered or offered only through an inference profile, and throttling. **No other region is
modelled**: decision 2 and Amendment 4 hold every Bedrock engine to London before an entry is made, so a call
elsewhere cannot be asked for (`test_model_engine_kinds.py`'s `bedrock-us`, `bedrock-ireland`, `id-*` and `arn-*`
cases), and the earlier case that called Bedrock in `us-east-1` was removed.

**Tests** (`process/lanes/platform-b/p11/RED_RECORD.md`, each red first or shown red by a fault planted at its call
site, `p11/plant.py`): `tests/services/api/test_model_engine_kinds.py`; `tests/adapters/model_litellm/
test_stand_in_engine_kinds.py`; `tests/cli/test_models_verb_iam_role.py`; `tests/harness/test_model_engines.py`
(main's own, unchanged: a plain provider's line as before); `Models.test.tsx`; `keyboard/admin-models.spec.ts` (two
cases, rule 13, each asserting the request's body); axe on two new *Models* states in the three themes.

**At the rebase onto P7, on the real profile.** Two render fixes, in P7's `harness/cloud_platform/` (platform's
files, so sent as `p11/cloud-platform-P11.diff` and applied at merge): the cluster translation is validated with its
engines held to cloud-platform's rules (`ENGINES_AS` in the validation's context, honoured only for that profile on
a cluster configuration), and a Bedrock engine's egress host is a row of `profile.yaml` by its kind
(`engine_kind_hosts: bedrock: bedrock-runtime.{region}.amazonaws.com`, ADR-148 Amendment 1 item 11's "a row, not an
edit to the render"), allowed by its networks or refused in words. Eight cases on this branch need the diff and pass
with it. **Carried to P7b:** a cloud-platform render runs the gateway only with an engine enabled at install, so an
engine first added in *Admin › Models* there has no gateway until the deployment is rendered again with it.

**Cost.** P2's limits are shown applied to each kind's own gateway key, not enforced on a call to either kind. The
administration guide's settings appendix (generated from the schema) is the docs lane's file: its change is sent as
`p11/docs-admin-guide-P11.diff` (regenerated against the 1.73 guide), and `tests/test_admin_guide.py` fails twice on
this branch until it is applied.
