# SE6b, stopped at round 8: every fault, and what is left (for the owner, 22 November 2026)

**State.** SE6b (a removed dashboard identity's rows leave the reporting mart; backlog N19) **stopped at its limit of eight rounds** with **one fault in behaviour and no test gap** at tip `1f7e947355`. **No further round was started.** It has not merged: the standing accept does not cover a fault.

## The faults, round by round (a verifier's round N finding is fixed in round N+1)

| Round | Tip | What the verifier found | Closed in |
| --- | --- | --- | --- |
| 1 | `6d04111187` | `record_failure` is an unconditional upsert: a refused feed pull (or a pass running during the removal) rewrote a removed identity's `pulls` row; a refusal's words did not reach the Admin screen; plus a test gap (the feed-refusal path untested) | round 2 |
| 2 | `f3e1b309ea` | When the identity was deleted at the provider and the mart then failed, the route answered 503 **before** writing the `remove_dashboard` audit row | round 3 |
| 3 | `e6cf6dbfae` | The rollback undid the purge and the stamp when the mart failed after the provider's delete; later refused pulls rewrote the rows; nothing in the product could clear them | round 4 → replaced by the round-5 design |
| 4 | `958e14aebc` | The 503 told the administrator to remove the identity again, but after a reload it is gone from the list, so no Remove button; plus a test gap (no route test raised Keycloak's `NoSuchDashboard`) | round 5 (the new design: stamp first in its own transaction, hide stamped rows at once, then delete at the provider, then purge, the next sync finishing it) |
| 5 | `0c295550c3` | The stamp is lifted by any successful pull that began after it was written, so an identity whose provider delete failed looked like a re-registered one: its rows readable again at the next sync | round 6 |
| 6 | `2398f23421` | **Accepted narrower (two test gaps, backlog rows 15 and 16)**; the merge gate then refused it for one check (`test-file-coverage-check`: the test file imported `asyncpg`, which reads as live) | round 7 |
| 7 | `d03cbb9eec` | A failed delete at the provider (round 5, step 2) did not leave the rows hidden until the retry, and a gap (row security proved only against a hand-written fake) | round 8 |
| 8 | `1f7e947355` | **OPEN: the Conduit's own read of the mart does not hide a stamped identity.** `GET /v1/admin/dashboards` (`app.py` about line 18129) gets its figures from `ReportFreshness.by_dashboard`, and that query does not respect the removal stamp: when the identity provider's delete failed, the identity stays listed and the Admin's list still shows its `last_pulled`, `cases_pulled` (a count of its hidden `pulls` rows), `last_failure` (in words) and `failed_at`, all worked out from the rows the stamp hides | **none** |

**Cause.** Every round's fix opened a new branch on one path: the identity deleted at the provider and the mart then failing. The round-5 design (an order in which no step's failure leaves rows readable) closed the structure; round 8 found the one reader that design did not reach, **the Conduit's own Admin list, which reads aggregates, not the rows.**

**What a reader can see now, at the tip.** Superset's readers (Admin, Alpha, the guest role): nothing of a stamped identity's rows (row security, proved against the fake only: backlog row 16). **The Admin's own dashboard list: a count, two times and a failure sentence for a stamped identity that is still listed because the provider's delete failed.** Only an administrator reads that list, and only for an identity still on it. **No key, token or password is shown, logged or sent anywhere.**

## What I need from you (and my view)

"accept SE6b" (a line in `resume.tsv`; the Admin-list fault becomes a backlog row first among the open ones), "add a round" (one round for exactly that one query), or a cut. **My view: one more round for exactly that one thing,** because the fix is one query reading the same stamp the readers use, the exposure is an aggregate shown only to an administrator for a still-listed identity, and the slice closes the retention fault that has stood open since 19 November. **If you would rather not spend a round: accept it, with the Admin-list fault as the first backlog row and a note in the guide that a removal pending its provider delete shows its counts to administrators.** It does not merge until you say.
