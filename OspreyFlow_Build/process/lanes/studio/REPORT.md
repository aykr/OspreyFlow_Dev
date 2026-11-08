# studio lane · report · L1.2c (ADR-110 Amendment 16), with review round 1, 8 November 2026
1. **A returning row's own merge reverts: met.** A dropped row comes back and merges into its own withdrawn key's link. Its load keeps the link as it was, and its revert puts it back exactly. The returning load, the refresh and the first load unwind in that order. Any other merge still refuses (ADR-127 decision 6).
2. **Written since, by anyone (round 1, B1):** the load keeps a digest of the whole stored record as it left it (`left_digest`, `stored_digest`, schema `c228aa3` through the orchestrator). The revert's planning, and the restore inside its own transaction, refuse anything else: a later load, a correction, a revert, a re-stamp, a provenance strip. An untouched link reads back to the same digest (a conformance case).
3. **The other review items:**
   - B2: `withdrawn_row_links` is scoped to its recipe and case, proved on the real ledger.
   - B3: the stamping wrapper's restore carries L3.1's composite guard, and `__getattr__` refuses the name.
   - MF11: the restore writes its own type alone.
   - MF10: the put-back link leaves every working set, and the change is published for the case.
   - Item 7: a merge that raised the action code is put back at the marking before.
4. **Rule 3:** no route, view, report or metering carries the prior state. A SECRET link stays SECRET. The refusal names no other load or case.
5. **Red on record** (`L1.2a_RED_RECORD.md`, `plants/plants5.py`): O1–O10 offline; L0–L5, L3 on the cited file, and W1 and W2 under the lease.
6. **Leases:** studio "L1.2c round 1 live: …", 02:10:46Z–02:19:17Z, and the whole graph conformance suite, 01:23:56Z–01:39:55Z (341 passed). `pgrep`, `lsof` and `docker ps` were checked before and after, and the stack is stopped.
   - Green: link-state conformance 9 of 9; live files 28 of 28; units 137 of 137 offline.
7. **Item 8, cost:** the 6,838-row PIN-call refresh took 93.70s with the capture and 88.14s without (+6%, one run each, no row returning).
8. **Found, main's, reported:** `upsert_edges`' merge writes by id alone (`g.E().has("id",…)`), so a merge rewrites every type that holds the id.
9. **Known limit, recorded in Amendment 16:** a rerun after a part-way revert has no end-to-end test yet.
10. **My slip:** an offline run with the leased ports exported, without the lease. Nothing was reached; it's now guarded on main.
11. **Next, agreed with case and the orchestrator:** L3.1b's `model_version` and the Test run's draft version, then Part B, then L3.1b's screens. I've ratified case's `flag_for_model`, on conditions.
