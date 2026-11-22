# SE8c, before round 9: every case, open or closed (the line's table before a round of 5 or more; 22 November 2026)

The fuller table, with each cause and the pattern, is `OspreyFlow_Build/process/lanes/v062/SE8c_ROUNDS_TABLE_2026-11-21.md`; this is its record for the line. Round 9 is **the owner's one added round (file 011)**, for **one test only**; the slice does not merge until it is in and verified.

| Verifier of round | Kind | What | Status |
| --- | --- | --- | --- |
| 1 | test gaps (2) | No test covers the one `lifespan` line that installs the sign-in watch; the page service's leak scan leaves the identity provider's address out of its log check | closed (round 2) |
| 2 | fault | A second real sign-in or sign-out within one identity-provider session was not recorded (the "already recorded" key was the provider's session) | closed (round 3) |
| 3 | fault, gap | The check for "no identity-provider setting changed" applied to every branch; the acceptance test had no scan row | closed (round 4; the scan row was the conductor's, committed) |
| 4 | fault | The per-deployment HMAC secret cached in each process for ever | closed (round 5) |
| 5 | fault | The first sight of a session was not recorded when a person signs in to Superset on Entra ID (`get_principal` calls `note_seen` only when `identity.routes is None`) | closed (round 6) |
| 6 | faults (2) | The route reachable through the page service's own `/v1` forwarder; the "forget it again" repair covered only `AuditWriteError` | closed (round 7 partly; the route closed at the route in round 8) |
| 7 | faults (2) | The route still reachable through the workspace's proxy and accepting any client's token; the first sight not recorded on the delta socket's bearer-header path | closed (round 8: no fault found by the round-8 verifier) |
| 8 | test gap (1) | The route's client check is tested on Keycloak only: no test sends a request through the route with an Entra mapping | **OPEN: round 9's one test** |

**Totals:** eight faults found (rounds 2 to 7), all closed; four test gaps (rounds 1, 3, 8; one of round 3 the conductor's), three closed, one open. **Open now: the Entra-mapping test (round 9).** **Converged:** round 8 found no fault. Nothing here names a key shown, logged or sent anywhere.
