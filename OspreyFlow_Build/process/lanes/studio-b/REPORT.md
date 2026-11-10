# studio-b · L1.10, the deployment's marking ceiling (ADR-148 decision 10, Amendment 2) · on main f2ef3b3

1. **The setting:** `deployment.highest_marking`, rendered as `OSPREY_HIGHEST_MARKING`; when it is not set, the ceiling is the scheme's highest. An unknown value stops the Conduit's start. It is in the guide's appendix A (1.66, this lane's row; the guide is the docs lane's).
2. **The refusals** (`services/ingest/ceiling.py`) come before anything is written. Their words name the limit, never the content.
   - **Loads:** `run_recipe` judges each distinct classification combination once; a row above the ceiling, or one whose classification cannot be read, refuses the whole load. A staged pipeline's fixed markings are judged before its step tables are written.
   - **Imports:** document and entity-picture uploads get a 422 `above_the_deployments_highest_marking`.
   - **Backstop and packs:** `dataset_scope`'s upserts, bulk loads and supersedes refuse too. `seed_internal` refuses a pack up front; cyber-intrusion and PaySim declare OFFICIAL.
3. **Read and write** (Amendment 2): read-side fallbacks stay at the scheme's highest; only writes are capped.
4. **Tests, plants, reviews:** 4 test files. 26 plants (`l1.10/red_plants.py`), each red for its reason; green 35. Two lane-review rounds, all 11 must-fixes and the minors fixed.
5. **Gates:**
   - **Live**, stack d at 47a2e15 (`l1.10/live-47a2e15.*`): 3,292 passed and 35 failed, all the run's, plus main's `test_schedule_notice` collection error.
   - **make test** at a38f8b4: 10,558 passed and 4 failed; vitest 2,968 passed and 1 failed. Three are host-bound; the lane's own two (citations, the guide's PDF) are fixed. **make -k ci:** red only for Docker.
6. **For admin:** `L1.10_system_ceiling.diff`, the ceiling shown on System.
7. **Carries:** the drawn item (case-b); promotion and drawn-merge writes (case); the cloud-platform OFFICIAL-SENSITIVE default (P7); the other packs' declarations; dropping a refused staged run's working tables; Verify judging the ceiling.
8. **Left:** L1.9 after P7. **Running:** nothing; no lease is held.
