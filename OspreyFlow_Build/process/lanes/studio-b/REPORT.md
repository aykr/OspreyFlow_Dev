# studio-b · L1.10, the deployment's marking ceiling (ADR-148 decision 10, Amendment 2) · on main f2ef3b3

1. **The setting:** `deployment.highest_marking`, rendered as `OSPREY_HIGHEST_MARKING`; when it is not set, the ceiling is the scheme's highest. An unknown value stops the Conduit's start (`CeilingUnknown`). The setting is in appendix A of the administration guide (1.66) and its mirror.
2. **The refusals** (`services/ingest/ceiling.py`) come before anything is written. Their words name the limit, never the content.
   - **A load:** `engine.run_recipe` judges every row's classification, each distinct combination once. A row above the ceiling refuses the whole load, and so does one whose classification cannot be read.
   - **A staged pipeline:** its fixed markings are judged before its step tables are written.
   - **An import:** a document or entity-picture upload gets a 422 `above_the_deployments_highest_marking`.
   - **The backstop:** `dataset_scope`'s upserts, bulk loads and supersedes.
   - **Demo packs:** `seed_internal` refuses a pack above the ceiling before it starts. Cyber-intrusion and PaySim declare OFFICIAL.
3. **Read and write** (Amendment 2): read-side fallbacks stay at the scheme's highest; only writes are capped.
4. **Tests:** 4 files. Plants: 26 in `l1.10/red_plants.py`, each red for its reason; green 35.
5. **Reviews:** two lane-review rounds, all 11 must-fixes fixed, along with the minors.
6. **Gates:**
   - **Live** on stack d at 47a2e15 (`l1.10/live-47a2e15.*`): 3,292 passed and 35 failed, all the run's, plus main's `test_schedule_notice` collection error.
   - **make test** at a38f8b4: 10,558 passed and 4 failed; vitest 2,968 passed and 1 failed. Three failures are host-bound. Two were this lane's own (citations, the guide's PDF), and both are fixed.
   - **make -k ci:** red only for Docker.
7. **For admin:** `L1.10_system_ceiling.diff` shows the ceiling on System.
8. **Carries:**
   - the drawn item: case-b;
   - the promotion and drawn-merge writes: case;
   - the cloud-platform OFFICIAL-SENSITIVE default: platform's P7;
   - the other packs' declarations;
   - dropping a refused staged run's working tables;
   - Verify judging the ceiling.
9. **The guide:** the docs lane owns it, and 1.66 is this lane's row (appendix A only).
10. **Left:** L1.9 after P7. **Running:** nothing; no lease is held.
