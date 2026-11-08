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

Live, under the platform lease on stack a (released after each run): the pinned gateway and a stand-in
provider (`fakeprov.py`) on a network of the lane's own, `OSPREY_LIVE_GATEWAY_URL=http://127.0.0.1:54400`.
`test_model_gateway_live.py`: the key round trip (1 passed, about 140 s) and the usage, rate and budget
case (1 passed, twice back to back: 32 s and 28 s, at 18:36 and 18:37 UTC).
