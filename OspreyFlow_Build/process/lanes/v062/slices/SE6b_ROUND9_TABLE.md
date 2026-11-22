# SE6b, before round 9: every case, open or closed (the line's table before a round of 5 or more; 22 November 2026)

The full table with causes is `OspreyFlow_Build/process/lanes/v062/SE6b_ROUNDS_TABLE_2026-11-22.md`; this is its record for the line. Round 9 is **the owner's one added round (his `add-round` line)** for **one query only**.

| Verifier of round | What was found | Status |
| --- | --- | --- |
| 1 (`6d04111187`) | `record_failure` rewrote a removed identity's `pulls` row; a refusal's words did not reach the Admin screen; a test gap on the feed-refusal path | closed (round 2) |
| 2 (`f3e1b309ea`) | the route answered 503 before the `remove_dashboard` audit row | closed (round 3) |
| 3 (`e6cf6dbfae`) | the rollback undid the purge and the stamp after the provider's delete; later refused pulls rewrote the rows | closed (round 4, then the round-5 design) |
| 4 (`958e14aebc`) | the 503 told the administrator to remove again but the Remove button was gone; no route test raised `NoSuchDashboard` | closed (round 5) |
| 5 (`0c295550c3`) | the stamp lifted by any successful pull, so the rows were readable again at the next sync | closed (round 6) |
| 6 (`2398f23421`) | accepted narrower (backlog rows 15 and 16); the gate refused one check (the test file imported `asyncpg`) | closed (round 7) |
| 7 (`d03cbb9eec`) | a failed delete at the provider did not leave the rows hidden until the retry; a gap (row security proved only against a fake: row 16) | closed (round 8); the gap is backlog row 16 |
| 8 (`1f7e947355`) | **the Conduit's own Admin dashboard list (`ReportFreshness.by_dashboard`) does not respect the removal stamp: it shows `last_pulled`, `cases_pulled`, `last_failure` and `failed_at` of a stamped identity** | **OPEN: round 9's one query** |

**Totals:** eight rounds; every fault closed but the last; **open now: the Admin list's query.** Also open, not for round 9: backlog row 15 (the `dashboard_is_current` function callable by the reader login: the owner's call) and row 16 (the row-security claim against a real Postgres). **Convergence:** a fault in every round, each on the same path; round 8's is the smallest (an aggregate shown only to an administrator for a still-listed identity). No key, token or password was shown, logged or sent in any round.
