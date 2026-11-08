# Platform lane · P3 · red record (each new test shown red by a plant at its real call site)

## Carried from P2's independent review (commits e56300a, a1f9adc, 41c7ff3)

| Test | Plant | Red |
| --- | --- | --- |
| `tests/adapters/model_litellm/test_stand_in_gateway_usage.py::test_a_key_given_models_is_refused_any_other_model_in_the_measured_words` | the stand-in's models check removed | 1 failed |
| `…::test_the_key_list_is_hashes_newest_first_a_hundred_a_page_at_most` | the stand-in's size cap raised to 1000 | 1 failed |
| `tests/services/api/test_model_engine_keys.py::test_a_changed_master_key_revokes_every_engine_key_the_new_one_would_not_derive` | the reconcile's revoke removed | 1 failed (and the paging case) |
| `…::test_one_engine_s_key_is_refused_on_another_engine_s_models` | `models` not sent with the engine's key | 1 failed |
| `…::test_every_page_of_the_gateway_s_keys_is_read_before_revoking` | the first page of `/key/list` alone | 1 failed |
| `…::test_a_garbled_first_answer_never_stops_the_conduit_starting` | the first `start` catching only `ModelAdminRefused` | 1 failed |
| `…::test_an_empty_master_key_derives_no_engine_key` | `GatewayAdmin`'s blank-master check removed | 2 failed |
| `…::test_a_hosted_engine_named_local_is_refused` | the `local` name check removed | 1 failed |
| `…::test_test_the_connection_is_tagged_as_the_engine_s_test_job` | the tag not passed | 1 failed |
| `apps/workspace/src/patterns/QueryBuilderPanel.test.tsx` › shows an engine's limit reached in the Conduit's words | `model_limit_reached` misspelt in `patterns/api.ts`'s list | 1 failed |

## Measured first (rule 15), the pinned gateway (`ghcr.io/berriai/litellm@sha256:d295634e…`), a stand-in provider, no hosted provider called

- Platform lease on stack a, about 20:45:50–20:46:32 UTC: a key made or updated with `models` is refused any
  other model, held or not, 403 `key_model_access_denied`, naming the allowed models, never the key;
  `/key/update` changes `models` at once. `GET /key/list` answers SHA-256 hashes, newest first;
  `return_full_object=true` adds `token` (the hash), `key_name` (`sk-...` and the last four), `metadata`;
  `size` at most 100 (422 above); `total_count`, `current_page`, `total_pages`. `POST /key/delete` takes a
  hash (200; an unknown hash 404); the deleted key's next call is 401.
- Platform lease on stack a, 20:52:21–20:54:02 UTC: after three calls with an engine key (and about 75 s),
  its SHA-256 is in `LiteLLM_VerificationToken` (left out of every backup) and in `LiteLLM_SpendLogs`,
  `LiteLLM_DailyTagSpend` (which the usage reads), `LiteLLM_DailyUserSpend` and `LiteLLM_DailyTeamSpend`.
