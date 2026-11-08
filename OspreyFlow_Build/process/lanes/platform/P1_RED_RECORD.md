# Platform P1 · red-then-green record (rule 15)

Each plant at the real call site, run, then restored; 8 November 2026.

| Test | Plant | Red |
| --- | --- | --- |
| `tests/harness/test_egress_consequence.py` | none needed: the legacy `_egress_consequence` (reads only `hosted_fallback`) | 3 failed (`egress_exception` False for `providers`, the single `provider`, and no sendable codes) |
| `test_connection_check.py::test_a_retest_right_after_a_failure_says_try_again_in_a_minute` | `classify` without the cooldown branch | 1 failed |
| `test_connection_check.py` (words, fragment) | the check's words carry the gateway's response body | 6 failed, incl. `test_the_echoed_key_fragment_never_reaches_the_result` |
| `test_stand_in_gateway.py` | the stand-in accepts any provider key | 4 failed (stand-in's own refusal and cooldown cases, and two connection cases) |
