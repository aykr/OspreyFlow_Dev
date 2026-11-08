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
