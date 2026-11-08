# Platform lane · P2 · red-then-green record (rules 12 and 15)

Each test below was run with the named plant at its real call site and seen to fail, then run
against the code as committed and seen to pass. Offline runs use the port guard's dummy ports.

| Test | Plant | Red |
| --- | --- | --- |
| `tests/schemas/test_model_admin_limits.py::test_a_budget_without_its_period_or_tokens_is_refused` | `EngineLimits`' validator made to pass | 2 failed |
| `tests/adapters/model_litellm/test_stand_in_gateway_usage.py` (the stand-in's own proof) | the budget check removed | 1 failed (the budget case) |
| same | the rate check `>` for `>=` (the crossing call refused one late) | 1 failed (the request rate) |
| same | any virtual key allowed to read the activity | 1 failed (only the master key reads it) |
| `tests/services/api/test_model_usage_and_limits.py::test_the_figures_equal_a_planted_gateway_record` | `read_usage` takes `succeeded` from the calls | 1 failed |
| `…::test_the_figures_equal_a_planted_gateway_record`, `…counted_by_engine_and_job`, `…no_prompt_answer_key_or_source_id…` | `read_usage` reads every tag, not only `osprey:<engine>/<job>` | 3 failed |
| `…::test_a_request_rate_set_stops_the_next_request_through_the_real_routing`, budget, what a person sees, audit | `set_limits` never sends the limits to the gateway | 4 failed |
| `…rate…`, budget, what a person sees, `…go_with_the_engine_s_own_key…` | the client sends every call with the master key | 4 failed |
| `…::test_no_request_to_the_gateway_carries_a_person_s_id` | the client adds `user` with the person's id to each call | 1 failed |
| `…no_prompt_answer_key_or_source_id…` and three others | the client tags each call with the prompt's first words and the reader reads every tag (both at once) | 4 failed |
| `test_model_admin_routes.py::test_every_models_route_refuses_a_principal_without_manage_models` (both principals) | `manage_models` removed from the usage route | 2 failed |
| same | `manage_models` removed from the limits route | 2 failed |
| `…budget…`, `…priced_a_unit_a_token…` | hosted entries made without a price | 2 failed |
| `…rate…`, what a person sees | the gateway's refusal (naming the key's hash) put into the words | 2 failed |
| `…budget…` | the budget refusal's words (naming the key's last four) put into the words | 1 failed |
| `apps/workspace/keyboard/admin-models.spec.ts` "an engine's limits are set by keyboard" (and the registry's assertion) | the limits form's save made a plain button, never submitting | 2 failed |
| same, "the usage's period is chosen by keyboard…" (and the registry's assertion) | choosing a period never asks the Conduit again | 2 failed |
| `tests/services/api/test_model_gateway_live.py::test_usage_a_request_rate_and_a_token_budget_against_the_real_gateway` (live, platform lease, stack a, a freshly started pinned gateway) | hosted entries made without a price (and the price read-back removed) | 1 failed: DID NOT RAISE ModelLimitReached — the real gateway never stops an unpriced budget |
| `test_model_usage_and_limits.py::test_no_engine_key_or_master_key_reaches_any_log_record` (found by the lane before its review) | none: as first built, `put_engine_key` asked `GET /key/info?key=<engine key>`, and httpx logs every request's address at INFO | 1 failed (the engine's key in the log); fixed by updating first and making on its 404, the key only in bodies |

**After the lane's own review** (the `lane-reviewer`, 8 November 2026, on the branch at 03dbcfc):

| Test | Plant | Red |
| --- | --- | --- |
| `tests/harness/test_gateway_backup.py::test_a_backup_holds_no_engine_key_of_the_gateway` | none: as first built, the gateway's key table (`LiteLLM_VerificationToken`) was in the backup | 1 failed; then shown again with the table taken out of the exclusions |
| `tests/adapters/model_litellm/test_usage.py::test_any_other_429_is_not_an_engine_s_limit` | none: as first built, any 429 typed `throttling_error`/`budget_exceeded` was a limit; then with the gateway's words check removed | 2 failed (a provider's 429, a budget type in other words); 1 failed |
| `…::test_an_engine_of_any_name_the_schema_takes_comes_back_from_its_tag` | none: as first built, an engine's name was read up to 24 characters; then the cap put back | 1 failed each time |
| `test_model_usage_and_limits.py::test_a_refused_removal_of_the_engine_s_key_leaves_it_answering` | the credential removed before the engine's key | 1 failed |
| `…::test_a_gateway_unreachable_at_start_is_tried_again_until_the_engine_s_key_exists` | no background retry after a failed start | 1 failed |
| `…::test_no_request_to_the_gateway_carries_the_asking_person_s_id` (through the analyst's own extraction route, as a principal with a recognisable id) | a `user` in the client's body; a header naming the person | 1 failed each |
| `…::test_a_person_stopped_by_a_limit_is_told_so_in_words_through_their_own_route` | the limit's exception handler removed | 1 failed |
| `…::test_every_page_of_the_gateway_s_records_is_counted`, `…refused_in_words_never_cut_short` | the reader stops after its first page | 2 failed |
| `test_model_admin_routes.py::test_every_models_route_refuses…` (now asserting the gateway saw no request at all) | `manage_models` removed from the usage route | 2 failed |

**After the second review round:**

| Test | Plant | Red |
| --- | --- | --- |
| `test_model_usage_and_limits.py::test_a_retry_that_meets_an_unexpected_answer_keeps_trying_and_shutdown_stays_clean` | the retry catching only `OSError` (a 200 that is not JSON then ends it) | 1 failed |
| `…::test_a_page_that_does_not_say_whether_more_follows_is_refused_in_words` | the page's `has_more` and `total_pages` check removed | 1 failed |
| `test_model_gateway_live.py::test_the_real_pg_dump_leaves_out_every_sealed_row_of_the_real_gateway` (live; the case now makes an engine key and names each table rather than reading the list under test) | `LiteLLM_VerificationToken` taken out of the exclusions | first **passed** (the case read its tables from the list it tested, so a table dropped from the list was dropped from the check, the second review's finding); with the tables named, 1 failed (the key's row in the kept dump), then 1 passed |

Live, each under the platform lease on stack a (`stack_lease.sh acquire platform …`; released after each),
the pinned gateway and a stand-in provider (`fakeprov.py`) on a network of the lane's own,
`OSPREY_LIVE_GATEWAY_URL=http://127.0.0.1:54400`:
- lease taken about 18:13 UTC: the key round trip and the first usage case (2 passed, 170 s, 18:14–18:17);
- lease taken about 18:20 UTC: the usage case twice back to back after its fixes (1 passed each, 32 s and
  28 s, 18:36 and 18:37); the unpriced red on a freshly started gateway;
- lease taken 19:07:39 UTC (released 19:12:59): the paging and spend-delay measurements, then, on the
  changed key path, the key round trip and the usage case (2 passed, 170 s, 19:09:48–19:12:39) and the
  real `pg_dump` with the key table left out (1 passed, the table holding a row).
- lease taken 19:19:40 UTC (released 19:22:32): after the second round, the budget with no wait, the key
  round trip and the `pg_dump` with an engine key made (3 passed, 140 s, 19:19:53–19:22:14);
- lease taken 19:22:50 UTC (released 19:23:09): the `pg_dump` case with its tables named, red with the key
  table's exclusion removed, then green.
