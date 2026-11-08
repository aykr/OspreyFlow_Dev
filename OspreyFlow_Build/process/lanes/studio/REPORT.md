# studio lane · report · L1.2b (Part B, phase 6's exit; ADR-140 Amendment 10), with review round 1, 8 November 2026
1. **From scratch, guided, keys alone: met.** `keyboard/ingest-studio.spec.ts` builds the whole committed reports map, and the saved map must **equal** the YAML's (a JSON copy held to it by `tests/demo_fixtures/test_reports_map_fixture.py`). That covers 11 elements, 10 links, conditions, content, six handling parts each, the transform, literal and optional bindings, the ignored columns, the row key, and the marking columns on the draft's own settings.
2. **Expert edit of it: met.** An Extract fed by Map on the canvas; the map isn't saved again; Test, then Deploy.
3. **Live walk: met.** Lease studio "L1.2b live walk", 06:30:25Z–07:12:44Z, with `stack_lease.sh up`/`down`. It used a fresh Postgres database (dropped after), scratch repository, ingest root and analytics, and a Conduit on 127.0.0.1:18001; osprey-local-lite was untouched.
4. **The walk's figures** (`live/studio-reports-walk.spec.ts`, run 6, 07:10:13Z):
   - asserted: the stored map equals the committed one, and the run read 350 and rejected 1;
   - checked by script afterwards: the deployed YAML matches;
   - observed only: Test rejected row 17, the teaching row. Timings are indicative, as two offline runs shared the machine.
5. **Found and fixed:**
   - live only (B8): the Map editor could make no `MENTIONED_IN` link; it now judges ends as the load does;
   - ignore controls are named with their column (B2), and link buttons meet WCAG 2.5.3 (B7);
   - harness fakes that differed from the product (rule 15): B5 and B9.
6. **Review round 1: items 1–5 fixed.** Amendment 10 separates asserted, checked and observed figures, and names the non-fresh graph and the concurrent runs. `meaning()` forgives only nullable fields (B11). Wildcard mixed-list and system cases added (B10). The guide names the bindings and the pack-pin difference. The heading is as reserved, and your reservations file is reverted.
7. **Recorded, not resolved:** a new pipeline pins no pack (`{}`), where the seeded draft pins `niem: 3`, because it has no domain-model step; phase 5 settles it.
8. **Red on record:** B1–B11 and the walk, in `L1.2a_RED_RECORD.md`.
9. **Green:** `make ci` exit 0 at `51e3e07`. Studio vitest 391/391, keyboard 76/76, axe 76/76, `tsc` clean.
10. **`make test`:** 8,100 passed and 3 failed, none mine: the machine's `osprey.yaml`, `graphify-out` at the root, and the phone extraction (needs the leased object store on 9000).
11. **Requests:** land `process/lanes/studio/L1.2b_action_registry.diff` (one id) with the merge, and mark the Amendment 10 reservation written.
12. **Slips, mine:** the harness's first reports source carried marking columns no person can register; the first JSON copy named the Build folder; I edited your reservations file (reverted).
13. **Next:** paused at the end of L1.2b, as the owner asked. Nothing is running and no lease is held.
