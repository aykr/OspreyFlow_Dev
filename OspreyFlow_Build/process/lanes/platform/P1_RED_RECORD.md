# Platform P1 · red-then-green record (rule 15)

Each plant at the real call site, run, then restored; 8 November 2026.

| Test | Plant | Red |
| --- | --- | --- |
| `tests/harness/test_egress_consequence.py` | none needed: the legacy `_egress_consequence` (reads only `hosted_fallback`) | 3 failed (`egress_exception` False for `providers`, the single `provider`, and no sendable codes) |
| `test_connection_check.py::test_a_retest_right_after_a_failure_says_try_again_in_a_minute` | `classify` without the cooldown branch | 1 failed |
| `test_connection_check.py` (words, fragment) | the check's words carry the gateway's response body | 6 failed, incl. `test_the_echoed_key_fragment_never_reaches_the_result` |
| `test_stand_in_gateway.py` | the stand-in accepts any provider key | 4 failed (stand-in's own refusal and cooldown cases, and two connection cases) |
| `test_model_admin_routes.py::test_every_models_route_refuses_a_principal_without_manage_models` | `_MANAGE_MODELS = []` (the right check removed from every Models route) | 2 failed (analyst; every other administration right) |
| `test_model_admin_routes.py::test_a_planted_key_appears_in_no_response_log_audit_file_or_gateway_row` | `log.info("setting key %s", key.get_secret_value())` in `ModelAdmin.set_key` | 1 failed |
| same | the key route takes `body: KeyInput` (FastAPI's validation, whose 422 echoes the input) | 1 failed |
| `test_model_engines.py::test_no_service_but_the_gateway_reads_its_encryption_key_or_database_password` | the salt's blank removed from `_gateway_database` | 1 failed |
| `test_model_engines.py::test_the_gateway_s_secrets_are_minted_once_and_kept_by_every_apply` | the salt named `OSPREY_LITELLM_SALT_KEY` (a name `keep_existing_secrets` does not keep) | 5 failed, this one among them |
| `test_gateway_backup.py::test_a_set_sealed_under_another_key_is_refused_naming_each_key_lost` | `run_restore` without `check_gateway_key` | 1 failed |
| `test_cluster_render.py::test_no_workload_but_the_gateway_reads_its_encryption_key_or_database_password` | none needed: it found the cluster's own `worker` workload unblanked when the blanks lived in the compose render; fixed in `harness/cluster.py`'s post-pass | 1 failed, then green |
| `tests/cli/test_models_verb.py::test_models_key_hands_the_key_over_by_name_and_restarts_nothing` | the key appended to the `docker compose exec` argv | 2 failed |
| `tests/cli/test_doctor_model_keys.py::test_the_doctor_names_each_lost_key_as_a_warning` | `_doctor` passing `model_states=None` (not asking the deployment) | 1 failed |
| `apps/workspace/src/admin/sections/Models.test.tsx` "shows the Conduit's refusal in its words and still never the key" | the key field not cleared after sending | 1 failed |
| `keyboard/admin-models.spec.ts::every registered Models action has its own proving test case above` | one case's `registerCovered` removed | 1 failed |
| `a11y/every-harness.spec.ts` on `models-harness.html` | none needed: the first scan found three key buttons whose names did not contain their visible text (2.5.3), fixed | 3 failed (dark, light, GOV.UK), then 16 passed |

## Live check, 8 November 2026 (platform lease on test stack a, since released)

The Conduit's own client (`GatewayAdmin`, `check_connection`, run from `ospreyflow/api:ci` with this branch's
`packages` and `services` mounted) against the pinned LiteLLM image with its own database and a stand-in
provider, on an internal-only Docker network (no provider reachable, synthetic keys):
credential + entry made (`osprey-openai-known-model`); wrong key → `key_refused`, no key fragment in the words;
rotated → `cooling_down` at once, `ok` after the cooldown; entry patched → `ok`; key removed → `key_refused`;
entry removed → `cooling_down` (**the stand-in said `not_routed`: corrected, with
`test_an_entry_deleted_while_cooled_down_still_answers_the_cooldown`**); unknown model → `not_routed`; PATCH of
an unknown id → refused in fixed words (HTTP 404); wrong gateway token → `gateway_token`, no token fragment.

## After the lane's own review (lane-reviewer, 8 November 2026)

| Test | Plant | Red |
| --- | --- | --- |
| `test_model_admin_routes.py::test_no_route_echoes_a_key_shaped_value_in_a_refusal` | the add route takes `body: EngineInput` (FastAPI's 422 echoes a key-shaped contract reference) | 1 failed |
| `test_model_admin_routes.py::test_a_gateway_that_refuses_leaves_the_models_file_and_routing_as_they_were` | `edit_engine` saves the file before the gateway answers | 1 failed |
