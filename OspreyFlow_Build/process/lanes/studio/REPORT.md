# studio lane · report · L1.2 (phase 6), after the second review, 7 November 2026
1. **Rule 4 at the class: met.** `get_authorized_studio_recipe` refuses, as missing, a recipe whose dataset is not the one the path's case loads into (`made_in`). A recipe with no dataset stays in reach, as `reach_clause` keeps such records. `test_studio_preview_routes.py`, for Preview and Test: red against today's dependency (200, not 404); another case loading into the same dataset still reaches the recipe; a viewer is refused (red with the level lowered). Spec 09 §8 states the rule.
2. **Phase 6's exit: NOT met.** The committed reports map (11 elements, 10 links, conditions, content, six handling parts bound to columns) has not been built from scratch in guided mode, by keyboard or by hand. The harness walk binds one Document's title. Nothing has been walked on the dev stack (no lease: case holds it). DEMO_GUIDE chapter 4 has no from-scratch steps. Left for the next step: the full walk and those steps. Met: `MapScreen` tests migrated; keyboard and axe green; spec 09 updated; the friction fragment.
3. **Minor items, done:**
   - publish refuses after a Preview (route test, red against `verify`); the other route tests' reds are on record;
   - the harness refuses without the approver role, at the save gate's 422, and for unready sample rows;
   - guided mode keeps the step that feeds an expert step (red case);
   - the reservation row is back to `reserved`; Amendment 8 names the owner's points (3, 5, 8) and says the exit is not met;
   - `workingSetOfDryRun` is shared; the preview audit carries `investigation_id`; the extra blank lines are gone.
4. **Found, not mine:** `test_load_checks.py`'s two verify cases fail on main's own `app.py` too (`KeyError: 'recipes_repo_root'`).
5. **Commits after main `4acbcec`, oldest first:** `5032dad 9c3eba7 5362702 5d8554a eaab8ee 931e874 36d3d51 1694c46 cdb4a0f f2543b1 f6f4c4c d0ba66e 680286d 9108c10 df08c13 0a11cba d6f7ff2 2eb7c61 10edbd4 39817f8 f0bee29 b620806 8c59653`, then this report.
6. **Request:** land `process/lanes/studio/L1.2_action_registry.diff` with the merge. It has 16 ids, and `ingest-studio.spec.ts` passes 36/36 with it.
7. **Hand check, no stack.**
   1. Run `cd /Users/ayankar/dev/osprey-wt/studio/OspreyFlow_Core/apps/workspace && npx vite --port 5185 --strictPort` and open http://localhost:5185/keyboard/ingest-studio-harness.html.
   2. Click *Open Visit bookings*, then *+ Extract*. Then *Map: Map*, *Preview* and *Run preview*.
   3. Then *Deploy* and *Deploy as v3*: refused, "hasn't passed Test".
   4. Then *Test*, *Run the test*, *Deploy* and *Deploy as v3*: deployed.
   5. Reload. Click *Open Visit bookings*, *Map: Map*, *Open map editor*, *Choose* on "called", *Entity 1: visitor (Person)* and *Bind called here: name*.
   6. Repeat on http://localhost:5185/keyboard/ingest-studio-harness.html?brand=govuk. Add `&expert=1` to see an expert step read-only.
8. **Green:** keyboard 549/549 (full suite); axe 72 (ingest states, three themes); vitest 338 (ingest); ruff, mypy, tsc; Python 1426 of 1427 in the Studio, recipe and route tests. The one failure, `test_a_pipeline_recipe_runs_through_the_pipeline_runner`, hit `asyncpg … pool is closed` mid-run and passes alone. **Questions for the owner:** none. **Running:** nothing of mine; no lease, no stack.
