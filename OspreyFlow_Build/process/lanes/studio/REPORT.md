# studio lane · report · L1.2b (Part B, phase 6's exit; ADR-140 Amendment 10), with review round 1, 8 November 2026
1. **From scratch, guided, keys alone: met.** `keyboard/ingest-studio.spec.ts` builds the whole committed reports map (11 elements, 10 links, conditions, content, six handling parts each, transform, literal, optional, 4 ignored columns, the row key, the six marking columns on the draft's own settings). The saved map must **equal** the YAML's, via a JSON copy held to it by `tests/demo_fixtures/test_reports_map_fixture.py`.
2. **Expert edit of it: met.** An Extract fed by Map on the canvas; the map isn't saved again; Test, then Deploy.
3. **Live walk: met.** Lease studio "L1.2b live walk", 06:30:25Z–07:12:44Z; `stack_lease.sh up`/`down`; a fresh Postgres database (dropped after); scratch recipe repository, ingest root and analytics; Conduit on 127.0.0.1:18001; osprey-local-lite untouched.
   - `live/studio-reports-walk.spec.ts`, run 6 (07:10:13Z): stored map equals the committed one; the run read 350 and rejected 1. Deployed YAML equal (checked by script after).
   - Observed: Test rejected row 17, the teaching row. Two offline runs shared the machine, so the timings are indicative.
4. **Found and fixed:**
   - live only (B8): the Map editor could make no `MENTIONED_IN` link. It read `*` as a type name, and now judges ends as the load does;
   - each ignore control is now named with its column (B2);
   - the link buttons now meet WCAG 2.5.3 (B7);
   - harness fakes that differed from the product (rule 15): it now refuses an unbound declared part and registers sources as a person can (B5, B9).
5. **Review round 1: items 1–5 fixed.**
   - Amendment 10 now separates asserted, checked-after and observed figures, and names the non-fresh graph and the concurrent runs.
   - `meaning()` forgives only schema-nullable fields (B11).
   - Wildcard mixed-list and system cases added (B10).
   - The guide names the bindings and the pack-pin difference.
   - `ADR_RESERVATIONS.md` is reverted to yours, and the heading is as reserved.
6. **Recorded, not resolved:** a new pipeline's Deploy pins no pack (`{}`), where the seeded draft pins `niem: 3`, because it has no domain-model step. Phase 5's removal of that step settles it.
7. **Red on record:** B1–B11 and the walk, in `L1.2a_RED_RECORD.md`.
8. **Green:** `make ci` exit 0 at `51e3e07`; `make test` 8,100 passed, 3 failed, none mine. Offline, closed ports.
   - The 3: `osprey.yaml`, the machine's own; `graphify-out` at the root; the phone extraction, which needs the leased object store on 9000.
   - Studio vitest 391/391, keyboard 76/76, axe 76/76; `tsc` clean.
9. **Requests:**
   - land `process/lanes/studio/L1.2b_action_registry.diff` (one id) with the merge;
   - mark the Amendment 10 reservation written.
10. **Slips, mine:**
    - the harness's first reports source carried marking columns no person can register;
    - the first JSON copy named the Build folder;
    - I edited your reservations file (reverted).
11. **Next:** paused at the end of L1.2b, as the owner asked. Nothing is running and no lease is held.
