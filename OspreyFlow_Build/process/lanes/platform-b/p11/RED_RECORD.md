# P11 part 1 · red record (rule 15), 11 November 2026, on the test server, offline (no stack)

Each refusal is shown red twice over: its test run red before the code it proves existed, and the fault
planted back at its real call site, one exact replacement in the shape that call site receives, and shown
red for its stated reason. The plants are `p11/plant.py` (committed, run from `OspreyFlow_Core`, offline
ports; it puts each file back, and since 11 November writes no bytecode while a plant runs). **Every plant
below was run again at the code head bcc51186**: `plants-bcc51186.txt`.

## Before any code
- First round: `test_stand_in_engine_kinds.py` collection error, then 2 red at the real classifier;
  `test_model_engine_kinds.py` 23 failed, 2 passed (`red-1-before-any-code.txt`).
- **The orchestrator's review, round 1** (`red-2-round-1-at-cec7a5e6.txt`): this round's tests run against the
  reviewed head's sources (cec7a5e6; the tests new). **The blocker, red for its stated reason**: a models file
  naming `bedrock` on `local-lite`, `small` and `cluster`, the Conduit's `OSPREY_MODEL_ENGINES` naming it, and a
  cluster `osprey.yaml` naming it all failed with "bedrock is reached only as Amazon Bedrock in London" (the
  three reader paths). The stand-in's new refusals all answered 200 (policy 403, 429, other shape, model not
  granted, expired) and the slash-ended address 500; the classifier read the expired role as `key_refused`.
  Most other cases errored on the new `ModelSettingsFile(profile=…)` argument, and the CLI file on the new
  `MODEL_ROUTE_PROFILE`: those are proven by their plants below, not by that run.

## Plants: the first round's, as each now stands (ids as before)
| # | Planted at | Fault | Test now red |
|---|---|---|---|
| 1 | `GatewayAdmin.add_entry` | every entry names a credential | `test_an_iam_role_engine_keeps_no_key_anywhere` |
| 2 | `ModelAdmin.set_key` | the IAM-role refusal removed | `test_an_iam_role_engine_keeps_no_key_anywhere` (`200 == 409`) |
| 3 | `ModelAdmin.edit_engine` | an address change keeps the key (all that is left of `_where_the_key_goes`, item 5) | `test_a_refused_reconcile_after_an_address_change_says_no_key_rather_than_key_set` |
| 4 | `model_keys.move_keys` | a key moved for an IAM-role engine | `test_the_command_line_moves_no_key_for_an_iam_role_engine` |
| 5 | `ModelAdmin.routes` | an IAM-role engine offered only with a key | `test_bedrock_answers_through_the_gateway_pod_s_role_in_london` |
| 6 | `apply.provider_secret_lines` | the install asks every engine for a key | `test_the_install_asks_no_key_for_an_iam_role_engine` |
| 7 | `render.model_engines_env` | the kind not written | `test_the_render_tells_the_conduit_each_engine_s_kind_and_how_it_signs_in` |
| 8 | `model_routing.routes_from_env` | the role ignored | `test_an_iam_role_engine_has_no_key_variable_and_is_offered_with_none` |
| A | `cluster.render_cluster` | a held key not blanked | `test_an_iam_role_engine_s_held_key_is_blanked_in_every_cluster_workload` |
| B | `engine_refusal` | `bedrock` as a provider on cloud-platform | `…refuses_each_shape_amendment_7_does_not_allow[bedrock-named-provider]` |
| C | `engine_refusal` | the gateway by the role | `…[gateway-by-role-held]` |
| D | `ModelAdmin.edit_engine` | the kind changeable | `test_an_engine_s_kind_is_fixed_once_added_…` |
| E | `ModelAdmin.remove_key` | removal not refused | `test_an_iam_role_engine_keeps_no_key_anywhere` |
| F | `ModelAdmin._start_once` | no entries for a declared IAM-role engine | `…declared_iam_role_engine_gets_its_entries…`, `…keyed_engine_declared_beside_bedrock…` |
| G | `ModelAdmin.edit_engine` | "key set" kept after the credential went | `test_a_refused_reconcile_after_an_address_change_…` |
| H | `install_page._providers` | a key field offered for it | `test_the_install_page_offers_no_key_field_for_an_iam_role_engine` |
| I | `connection.classify` | STS's refusal unread | `test_bedrock_refuses_when_the_role_does_not_trust_…` |
| J | `connection.classify` | the inference-profile refusal unread | `test_bedrock_refuses_a_model_offered_only_through_an_inference_profile` |
| K | `ospreyflow.models._STATE_WORDS` | `iam_role` unknown to the CLI | `test_an_iam_role_engine_is_listed_as_keeping_no_key` |
| L | `ospreyflow.main._models` | `key`/`remove-key` not refused first | `test_models_key_and_remove_key_refuse_an_iam_role_engine_before_reading_a_key` |

The first record's plant 3 (`_where_the_key_goes`' sign-in and region parts, "signing in another way") cited a
test that no longer existed: those parts were unreachable (the kind is fixed, each kind has one sign-in,
Bedrock one region) and are removed (item 5); plant 3 is now the address guard that remains. Plants 1 and 2
cited a parametrised `[bedrock, gateway-by-role]` that the first round's review had already narrowed to Bedrock.

## Plants: the orchestrator's review, round 1
| # | Planted at | Fault (item) | Test now red |
|---|---|---|---|
| N1 | `engine_refusal` | off cloud-platform, the two kinds taken (1) | `test_off_the_cloud_platform_profile_the_two_kinds_are_neither_offered_nor_taken` |
| N2 | `engine_refusal` | Amendment 4's rules on every profile: the blocker itself (1) | `test_a_models_file_naming_bedrock_loads_off_the_cloud_platform_profile_as_before` and the other off-profile cases |
| N3 | `ModelSettingsFile.load` | the file's engines not checked (1, 2) | `test_the_conduit_refuses_a_cross_region_id_however_it_arrives` |
| N4 | `Installed.from_env` | the start's engines not checked (1, 2) | the same |
| N5 | `ModelAdmin._validated` | Admin › Models ignores the profile (1) | `…refuses_each_shape…`, `…neither_offered_nor_taken` |
| N6 | `OspreyConfig._engines_suit_the_profile` | `osprey.yaml` ignores the profile (1) | `test_osprey_yaml_off_the_cloud_platform_profile_…` |
| N7 | `engine_refusal` | an inference profile's id or an ARN taken (2) | `…refuses_each_shape…[id-*, arn-*]` |
| N8 | `_address_refusal` | userinfo taken (4) | `test_a_planted_token_appears_in_no_response_…` (the paste's own shape) |
| N9 | `_address_refusal` | a query or fragment taken (4) | the same |
| N10 | `engine_refusal` | a key-shaped label taken (4) | the same |
| N11 | `connection.classify` | Bedrock's model access read as the role (3) | the stand-in's and the route's model-access cases |
| N12 | `connection.classify` | Bedrock's expiry read as the role (3) | the stand-in's, the documented wording's and the route's expiry cases |
| N13 | `KIND_WORDS` | the gateway's 403 said as the token alone (3) | `test_the_gateway_s_policy_refusal_names_the_policy_…` |
| N14 | `ModelAdmin.test` | another-shaped 4xx said as unreachable (3) | `test_the_gateway_s_refusal_in_another_shape_…` |
| N15 | the stand-in | the address matched only as written (3) | both trailing-slash cases |
| N16 | `ospreyflow.main._models` | a key read with the Conduit silent (8) | `test_with_the_conduit_silent_no_key_is_read_…` |
| N17 | `may_sign_in_by_role` | an Admin-added engine not held back on cloud-platform (8) | `…[added-in-admin-models-*]` |
| N18 | `ModelAdmin.view` | the two kinds offered on every profile (1) | `…neither_offered_nor_taken`, `…as_before` |
| N19 | `ModelSettingsFile.save` | a plain provider's file written with the new fields (1) | `test_off_the_cloud_platform_profile_the_models_file_and_render_are_written_as_before` |
| N20 | `render.model_engines_env` | a plain provider's line written with them (1) | main's own `test_the_conduit_is_told_the_engines_the_defaults_and_key_presence_never_a_key` |
| N21 | `ospreyflow.models.MODEL_ROUTE_PROFILE` | the CLI's profile drifts from the schema's | `test_the_command_line_names_the_profile_as_the_schema_does` |
| N22 | the stand-in | Bedrock grants a model not granted (3) | the stand-in's model-access case |
| N23 | `render.compose_services` (the gateway's environment) | a static AWS key named for the gateway (8) | `test_the_gateway_workload_carries_no_static_aws_key[*]` |
| N25 | the same | the gateway handed the whole `deployment.env` (8) | the same |
| N24 | `ModelAdmin.add_engine` | a plain provider's audit names the new fields (1) | `…written_as_before` |
| U1 | `Models.tsx` | the kind offered on every profile (1) | vitest "offers no kind of engine off the cloud-platform profile…" |
| U2 | `Models.tsx` | `bedrock` a provider by a key on cloud-platform | vitest "on the cloud-platform profile offers Bedrock as its own kind…" |
| U3 | `Models.tsx` | a plain provider sent with the new fields (1) | vitest, the same off-profile case |
| U4 | `Models.tsx` | the gateway added without its address (8) | keyboard "the organisation's own gateway is added…" (`toMatchObject` on the body) |
| U5 | `Models.tsx` | an engine of the two kinds sent as a provider (8) | keyboard, both new cases (the body) |

## What the plants found (rule 15 at work)
- **N23 was not red at first** (`plants-first-run-uncommitted.txt`): planted in `render_cluster`'s gateway
  branch, which never ran, because the cluster's gateway reads no Secret whole (no `envFrom`). That branch, the
  first round's own, was dead code: removed. The test also counted only `value`/`valueFrom` entries though the
  chart names secrets with `secret:`; it now asserts no `envFrom` and no AWS key name in any shape. N23 was
  planted again where a key would really arrive, the gateway service's own environment, with N25 beside it.
- **A stale `.pyc` outlived a plant.** N21's replacement kept the file's size and was put back within the
  second, so Python kept the planted bytecode and a later ordinary run failed on `cloud_platform`. The script
  now writes no bytecode while a plant runs and removes the planted file's after; the run at bcc51186 is clean
  of it, and every result above is from that run.

## The Glass, at bcc51186's code with `shared-files-P11.diff` applied
vitest `Models.test.tsx` 11/11; keyboard `admin-models.spec.ts` 13/13 (slot 7, `LANG=en_GB.UTF-8`); axe 27 scans
and 9 label checks over the nine *Models* states, the two new ones at `cloud=1`, dark, light and GOV.UK, 36/36.
