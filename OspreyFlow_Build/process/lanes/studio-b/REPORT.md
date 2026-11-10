# studio-b · brief L1.7a part 2 (the Studio's tips) and L1.7a's carries · gated at 5100bdb (main 865e097)

1. **Part 2, the tips** (ADR-145 Amendment 7): `L1.8_studio_tips.patch`, `L1.8_action_registry.diff` and `L1.8_every_harness.diff`, landed in order after L2.7. Three hunks were merged by hand against L2.7 (`L1.8_PATCHES.md`): the Model place's why-not line beside L2.7's `onDecided`, the harness rights line, and `proposed=1` beside `rights=none`.
   - The re-gates on the merged tree (`l1.8b/`): keyboard 108 (studio-tips, ingest-studio, sources-connectors, admin) and needs-you 6; axe 192, every state of both Studio harnesses in three themes; vitest 617.
   - Each hand resolution was planted red and restored green: the Model gate by `rightsGate.test.tsx`, the harness line by `ingest-studio.spec.ts`. `studio-tips.spec.ts` cannot see the harness line, which is recorded.
2. **L1.7a's carries, as ADR-140 Amendment 18** (Amendment 17 untouched). Each was red first (`l1.8b/red-carry-*.txt`):
   - A refused publish puts the file and index back as the current `HEAD` holds them, removes a recipe it does not hold, and refuses a `HEAD` that is no commit before the write.
   - The aside sweep removes only an aside that is empty or holds just `.git`; point 6's first-use wording is corrected, with a test.
   - The queued-wait window is widened; the seed's earlier runs are recorded as skipped.
3. **Plants:** 45 in `l1.7a/red_plants.py`, all red for their reasons at 5100bdb; green 62.
4. **Gates at 5100bdb** (`gates/5100bdb.*`, each failure explained):
   - make test: 10,368 passed, 2 failed; vitest 2,956 passed, 1 failed. All three are host-bound, as before.
   - make -k ci: red only for Docker.
   - Live on stack d (`l1.8b/live-5100bdb.txt`): the publish's live files, 23 passed; the slow seed, 2 passed and 2 failed (the rehearsal reset and the resolution job), neither from the publish.
   - The seed baseline on main 94a74c5 (`l1.8b/baseline-seed-main-94a74c5.txt`, stack d under studio-b's lease, a throwaway worktree, removed): the same 2 fail there, so they are main's.
5. **Reviews:** three lane-review rounds, every must-fix fixed. Minors left: the put-back logs nothing when it succeeds, and no test asserts `_initialise`'s cause.
6. **Left:** L1.10 (the marking ceiling), then L1.9 after P7. **Running:** nothing; no lease held.
