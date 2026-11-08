# studio lane · report · L1.2d (ADR-110 Amendment 18), 8 November 2026
1. **A link write names its type: met.** `upsert_edges`' merge and both of `supersede_edge`'s writes are typed (`hasLabel`). A merge or a correction of one type's link never touches another type's link holding the same id.
2. **An ambiguous id is refused:** `supersede_edge` and `read_link_state` raise the new `ports.graph.AmbiguousLinkId` where two types hold the id, changing nothing, never taking the first type found.
3. **Who meets it, and how:**
   - a route answers `409 link_id_ambiguous` in words naming no type (one app handler, ratified for it alone);
   - a true-positive close is refused whole and not closed (QF a);
   - a resolution run skips the one link, records the rest, and names it in its run result (the orchestrator's ruling);
   - a returning row's load keeps no prior state for such a link, and its revert refuses one that became ambiguous.
4. **Red on record** (`L1.2a_RED_RECORD.md`, `plants/plants5.py`): D4–D8 offline (the load, the revert, the route, resolution, the close); D1–D3 and L5 under the lease.
5. **Leases:** studio "L1.2d: three conformance cases green, plants D1-D3", 03:36:57Z–03:37:49Z, and "L1.2d: the reordered two-types case green, L5 red", 03:41:47Z–03:42:36Z. Each was checked before and after with `pgrep`, `lsof` and `docker ps`; case's offline run on the closed ports was the only other process. The stack is stopped.
   - Green: conformance 12 of 12; touched units 178 of 178 offline.
6. **Reordered, not weakened:** L1.2c's two-types restore case now reads and merges while one type holds the id, then adds the other. Amendment 18 refuses the read it used to make, and the case still shows the restore is typed (L5 red).
7. **Coordination:** glass was told before `adapter.py` changed; its L2.8b touches other functions. It knows the exception, the 409, and that its repoint journal must keep no record of a refused close. My test of the close's answer is against main's `_close`.
8. **On main, not part of this step:** the fast tier's fix `72a5cdc`. `unreverted_loads` now leaves out `own_key_merges` with the other element lists, a fix in the code, not the test.
9. **Spec:** ADR-110 Amendment 18, written as reserved, with who meets the refusal and how.
10. **Next:** L3.1b's pinned `model_version` (schemas through the orchestrator first) and the Test run's draft version, then Part B, then L3.1b's screens.
