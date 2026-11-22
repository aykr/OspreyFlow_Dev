# SE8c, before round 10: every case, open or closed (the line's table before a round of 5 or more; 22 November 2026)

Rows 1 to 8 are those of `OspreyFlow_Build/process/lanes/v062/slices/SE8c_ROUND9_TABLE.md` (every verifier finding of rounds 1 to 8). Round 9 (the owner's one added round) closed the last (the Entra-mapping test); **the round-9 verifier passed `21646c6004` with no finding.** Round 10 is for **the three checks the merge gate then refused** (the gate's own `make -k ci` and `make test`; the slice's checks command does not run them).

| # | Source | What | Status |
| --- | --- | --- | --- |
| 1 to 8 | verifiers of rounds 1 to 8 | eight faults (rounds 2 to 7) and four test gaps; see the round-9 table | all closed |
| 9 | round-9 verifier | no finding | the slice is verified |
| 10 | merge gate, 22 Nov | `make route-coverage-check`: `POST /v1/session-events` is documented in no Apache-scoped document and is not in the allowlist | **OPEN: round 10** |
| 11 | merge gate | `make test-file-coverage-check`: `OspreyFlow_Build/tests/services/api/test_sign_in_events_ingress.py` and `test_sign_in_events_store_faults.py` import `asyncpg`, so the check reads them as live-service files in no job | **OPEN: round 10** |
| 12 | merge gate | `tests/services/api/test_reports_viewer_journey.py::test_every_route_naming_no_right_is_one_weighed_for_the_viewer`: the route `record_session_event` names no right and is not weighed | **OPEN: round 10** |

**Totals:** 12 items; closed 9; open 3 (the gate's), all in how the slice meets the project's own checks, **none a behaviour of the route**. **Convergence:** the verifiers found nothing in round 9; the three gate refusals are the same kind as CO1's and SE6b's (a new route, new test files, the viewer journey's list), which the slice's checks did not run. No key, token or password was shown, logged or sent anywhere.
