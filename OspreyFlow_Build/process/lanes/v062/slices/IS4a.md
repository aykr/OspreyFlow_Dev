# Slice IS4a · IS4 · The Studio's Pipelines page: a pipeline's steps, read-only, as a server-rendered page

- **Build id:** IS4 (the pipeline canvas, IS1's answers E and F; slice id IS4a, the first of IS4's slices).
- **After:** nothing. IS5a0, IS5a and IS3 are merged.
- **Status of this brief:** cut by the conductor on 28 November 2026, on the owner's standing word (D274; RULINGS.md, 28 November about 06:05, item 6), from a scout's reading of main. **Re-read every line it cites before you rely on it.**
- **IS4's later slices** (not this one) are a node's drawer with a ten-row preview, the editing steps, "use it only" with the hold, and Test, Deploy and Show YAML. IS4m is the Map editor on Sigma: it waits for IS4 and WS4b (RULINGS.md, the IS rulings, item 8).

## What exists today (the scout, 28 November)

- **`spec/09_INGEST_STUDIO.md:20-25`:**
  - the pipeline canvas is a plain TypeScript module in the pages service;
  - there is one view, and rights decide what a person may do;
  - there is no staging container (ADR-140 Amendment 22, `spec/06_DECISIONS.md` about line 41384).
- **The node vocabulary and the left-to-right drawing:** `spec/ingest_studio_redesign/INGEST_STUDIO_REDESIGN_BRIEF_v2.md`, about lines 239 to 260.
- **The Studio frame and its tabs:** `apps/pages/modules/studio-frame.ts` (about line 32 names Pipelines). There is no Pipelines page or route yet.
  - The Studio pages to copy: `apps/pages/server/datasetMap.ts` (IS3) and the Releases page (IS5a), with their scenario files under `OspreyFlow_Build/tests/glass_trees/`.
- **The React workspace's canvas** (`apps/workspace/src/ingest/dag/PipelineCanvas.tsx`, nodes placed by `pipelineLayout`, joined by SVG) stays as it is.
- **No Sigma:** this page draws no graph library (ADR-152 decision 9 holds only Sigma pages).

## What

1. **The scenario first** (IS5a's convention): `OspreyFlow_Build/tests/glass_trees/test_pipelines_page_scenarios.py` and the scenario section it reads. It must be red on main.
2. **The Pipelines page in both trees, read-only, scripts off.**
   - It lists the reader's pipelines (recipes) for a dataset.
   - One pipeline's page draws its steps in order, left to right, as HTML. Each step shows its kind (from the vocabulary) and its name, and steps are joined by plain SVG or CSS.
   - There is a keyboard path to every step (rule 13). The keyboard and scripts-off cases go in the pages' folders.
   - The data comes from the read the Conduit already has for a recipe's content (`services/api/studio_recipes.py` and the recipe routes in `services/api/`). **If no route returns a pipeline's steps to the page service, stop with a question: no Conduit change in this slice.**
3. **Access control (rules 3 and 4):**
   - The page asks the Conduit as the person.
   - "No such pipeline" and "not allowed" use the same words.
   - It shows no count or step the person may not see.
   - Each read has its access-control test.
4. **The function row:** a `pipelines` row in `FUNCTIONS.yaml`, the route in each tree's `routes.yaml` and `pageList.ts`, and the harness's route list (the append-only lists). The route-pin and page-list checks must stay green.
5. **Not in scope:**
   - editing;
   - the drawer and its preview;
   - Connect, Profile, Checks, Verify and Publish in the drawer (the answer to the scout's question, (a): none are mounted in IS4a);
   - the hold and "use it only";
   - Test, Deploy and YAML;
   - the Conduit;
   - the React workspace.

**Questions:** answer (a) on the owner's standing word, unless one is the owner's own kind (keys, credentials, security findings, protected files, decision records, the server and the demo, anything public), which stops the slice.

Binding: process/CLAUDE.md rules 3, 4, 12, 13 and 15; British English.

**The scan map:** say in your report which files and folders `test_pipelines_page_scenarios.py` reads; the conductor writes its scan-map row before the merge.

## Acceptance test

- `OspreyFlow_Core/apps/pages/test/default/pipelines.test.ts`, red on main.
- `OspreyFlow_Build/tests/glass_trees/test_pipelines_page_scenarios.py`, red on main.

## Checks

- The pages' unit tests.
- The shared page gates: `test_pages_foundation.py`, `test_functions_yaml.py`, `test_no_react_check.py`, `test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`, `test_doc_citations_check.py`, `test_route_pins.py`, `test_page_lists_merge.py`, `test_pages_setting.py`.
- Ruff, lint, typecheck and `no_react_check`.

**Before your final report, run by hand the cheap checks the conductor will run again before the merge.**

## Where your scenario section goes (the owner, 28 November 2026 about 10:45)

If you add a section to `spec/08_ACCEPTANCE_SCENARIOS.md`, put it **directly after Scenario DM** (the Studio's dataset map) and before Scenario MS, not at the end of the file. Other parts in flight add theirs elsewhere, and the file has no union merge.
