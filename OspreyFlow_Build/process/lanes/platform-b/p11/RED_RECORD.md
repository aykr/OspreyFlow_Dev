# P11 part 1 · red record (rule 15), 11 November 2026, on the test server, offline (no stack)

Each test was run red before the code it proves existed, then each fault was planted at its real call site
(`/tmp/p11plants/plant.py`: replace one line, run, restore) and shown red for its stated reason.

## Before any code
- `test_stand_in_engine_kinds.py`: collection error (no `StandInClientGateway`/`StandInBedrock`); with the
  stand-in built, 2 red at the real classifier (`connection.classify` read Bedrock's "Unable to locate
  credentials" as `unreachable` and its 400 `ValidationException` as `unreachable`), green once it reads them.
- `test_model_engine_kinds.py`: 23 failed, 2 passed (`red-1-before-any-code.txt`). The two passing were
  refusals `extra="forbid"` already made (a region on the gateway, an unknown kind).

## Plants (each restored after)
| # | Planted at | Fault | Red |
|---|---|---|---|
| 1 | `GatewayAdmin.add_entry` | every entry names a credential, IAM-role ones too | `keeps_no_key_anywhere[bedrock, gateway-by-role]`: `{'litellm_credential_name'} == set()` |
| 2 | `ModelAdmin.set_key` | the IAM-role refusal removed | `keeps_no_key_anywhere[…]`: `200 == 409` |
| 3 | `_where_the_key_goes` | only the address removes a key | `signing_in_another_way[to-the-role, to-another-kind]`: the token still held |
| 4 | `model_keys.move_keys` | the CLI moves a key for an IAM-role engine | `command_line_moves_no_key`: `ModelAdminRefused` (every `apply` would fail) |
| 5 | `ModelAdmin.routes` | an IAM-role engine offered only with a key | `bedrock_answers_through…`: `key_present False` |

## The `osprey.yaml` path (an engine declared at install)
Before the code: `render_tells…` (the Conduit read Bedrock back as `kind='provider', auth='key'`),
`no_key_variable…` (`bedrock` given `OSPREY_MODEL_KEY_BEDROCK`) and `install_asks_no_key…` (`ApplyFailed`:
"OSPREY_MODEL_KEY_BEDROCK is not set") all red.

| # | Planted at | Fault | Red |
|---|---|---|---|
| 6 | `apply.provider_secret_lines` | the install asks every engine for a key | `install_asks_no_key…`: `ApplyFailed … OSPREY_MODEL_KEY_BEDROCK is not set` |
| 7 | `render.model_engines_env` | the kind not written | `render_tells…`: the Conduit refuses the engine ("only a Bedrock engine takes a region") |
| 8 | `model_routing.routes_from_env` | the role ignored | `no_key_variable…`: `{'bedrock': False} != {'bedrock': True}` |

## The lane reviewer's round (5773a0b)
Each new test was written against the reviewed code and each fix planted back out at its call site; all red.

| # | Planted at | Fault (reviewer's item) | Red |
|---|---|---|---|
| A | `render.keyless_model_key_variables` | an IAM-role engine's held key not blanked (1) | compose `workspace`: `None == ''`; cluster `workspace`: `None == ''` |
| B | `ModelProviderConfig` | `bedrock` accepted as a provider or gateway (2) | `[bedrock-named-provider]`, `[bedrock-named-gateway]`: did not raise |
| C | `ModelProviderConfig` | the gateway by the role accepted (5) | `[gateway-by-role-held]`: did not raise |
| D | `ModelAdmin.edit_engine` | the kind changeable (4) | `kind_is_fixed…`: `200 == 422`, the DPA mark carried to `kind: provider` |
| E | `ModelAdmin.remove_key` | removal not refused (11) | `keeps_no_key_anywhere`: `200 == 409` |
| F | `ModelAdmin._start_once` | no entries for a declared IAM-role engine (3) | `declared_iam_role…`: `entry_for(...) is None` |
| G | `ModelAdmin.edit_engine` | "key set" kept after the credential went (16) | `refused_reconcile…`: `'set' == 'none'` |
| H | `install_page._providers` | a key field offered for it (14) | `{'acme','bedrock','gemini'} == {'acme','gemini'}` |
| I | `connection.classify` | STS's refusal unread (7) | `…does_not_trust_the_gateway_s_service_account`: `'unreachable' == 'key_refused'` |
| J | `connection.classify` | the inference-profile refusal unread (7) | `…only_through_an_inference_profile`: `'unreachable' == 'model_not_offered'` |
| K | `ospreyflow.models._STATE_WORDS` | `iam_role` unknown to the CLI (6) | listed nowhere; and `models key bedrock` then answered 0 |
| L | `ospreyflow.main` | `models key`/`remove-key` not refused first (6) | `[key]`, `[remove-key]`: `0 == 1` (the key handed to the Conduit) |

UI: vitest's "offers no key field or key action…" and the two keyboard cases are red with the *Enter key*
button shown for an IAM-role engine. Keyboard 13/13 and axe 27 scans + 9 label checks (9 *Models* states,
dark, light, GOV.UK) green with `shared-files-P11.diff` applied, slot 7, `LANG=en_GB.UTF-8`.
