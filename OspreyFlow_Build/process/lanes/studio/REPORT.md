# studio lane · report · L1.2d (ADR-110 Amendment 18), with review round 1, 8 November 2026
1. **Every link write and state read names its type: met.** `upsert_edges`' merge, `supersede_edge(…, *, old_type)` and the restore each write their named type alone; `read_link_state(edge_id, edge_type)` reads its named type alone. Every caller passes the old `Edge`'s type: link changes, pictures, extraction's confirm and resolution's conflicts.
2. **Rule 3, the round's blocker:** the first fix's refusal searched every type and told the corrector another link holds the id. It's removed whole, so nothing searches and nothing is refused: `AmbiguousLinkId`, its 409, the close refused whole, resolution's skip and their tests all went.
3. **A returning row's own link is read by its recorded type (QG a):**
   - `RowElements.edge_types` (schema `2bc3a08`, through the orchestrator) and the ledger's `edge_types` column, added by the store's idempotent start-up DDL;
   - a row kept before is never captured, and its load stays refused as `merged_links`, which is tested in the unit suite and in the real ledger.
4. **Rule 12:** resolution reports `conflicts_recorded`, asserted through the trigger (`test_trigger.py`), run under the lease.
5. **Red on record** (`L1.2a_RED_RECORD.md`, `plants/plants5.py`): O1–O10 and D9 offline; D1–D3, L0–L5, W1, W2 and D10 under the lease.
6. **Lease:** studio "L1.2d round 1: …", 04:13:30Z–04:21:05Z. `pgrep`, `lsof` and `docker ps` were checked before and after; case's offline run on the closed ports was the only other process. The stack is stopped.
   - Green: conformance 12 of 12; ledger 16 of 16; the live files and the trigger.
   - Two of this round's test faults were caught and fixed under the lease: a re-stamp by the ontology's type name, and the scope case's old answer.
7. **Coordination:** glass was told before `supersede_edge` changed; only its new tests need `old_type`. Case accepted the stamping wrapper's change.
8. **Spec:** ADR-110 Amendment 18, rewritten to the ruling. `builders.py:498-499`, an access-filtered path read by id, is recorded as a minor.
9. **Slips, mine:**
   - a staging command named whole directories; the classifier refused it, and the round was staged by named files;
   - the three deleted test files went into `96a53c1`.
10. **Next:** L3.1b's `model_version` (schemas to the orchestrator first) and the Test run's draft version, then Part B, then L3.1b's screens.
