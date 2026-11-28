# Slice GG2e2 · GG2 · The live graph page's read-only actions, each with its keyboard case, and the live Matrix over the store's graph (with the strength and rarity sort)

- **Build id:** GG2 (the `working-set` row, as GG2e1)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:** GG2e1 (the live page and its store); GG2d (the Matrix's grid module and rows in `glass-shared`). **Its
  merge waits for WS4b** (decision 9). It may be written meanwhile.
- **Split:** the second of GG2e's two parts (the 26 November draft's question 1 (a)).
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. No question here is the owner's. **If O2 (`INDEX.md`) is answered (b)**, this part is unchanged: the
  live Matrix sorts by strength either way.

## What

GG2e1's page, `/cases/graph?case=<id>`, gains two things:
- **The canvas's read-only actions**, each named by id and each with its case in the GOV.UK keyboard folder (rule 13).
- **The live Matrix**: GG2d's two grids drawn by the module over the store's own graph, with no read of their own. Its
  rows change as the deltas arrive.

The Matrix carries the selection to the canvas and back, shows a row on the graph, and **sorts links by connection
strength and by their ends' rarity** (ADR-139 decision 6, `spec/06_DECISIONS.md:22653`). The two routes answer for
the working set, which is what this page draws. GOV.UK page only.

**The answers (each (a), and why):**

4. **(a) The read-only actions** (the 26 November draft's question 4), by id from `CANVAS_ACTIONS`
   (`packages/glass-shared/src/keyboard/actionRegistry.ts:87-203`):
   - `zoom-in-and-out-by-keyboard` (:88) and `fit-to-view-by-keyboard` (:89);
   - the legend: `legend-folds-by-keyboard`, `legend-leaves-out-a-link-type-by-keyboard` and `legend-moves-by-keyboard`
     (:90-92);
   - the focus ring: `focus-establishes-ring`, `tab-leaves-the-canvas` and `ctrl-arrow-cycles-ring` (:97-99);
   - walking: `ctrl-shift-arrow-walks-every-node`, `arrow-walk-forward` and `arrow-walk-backward` (:106-108);
   - `focused-node-is-announced` (:110);
   - `l-steps-through-the-focused-nodes-links` (:171).

   Selecting a node shows its label (GG2d's `defaultLabel`) and type in a plain panel. The inspector is GG3d1's.
   - **The registry's comment** "Pan, zoom and lasso are deliberately absent" (:80-82) is about the pointer's
     gestures. Zoom by keyboard is registered (:88) and is offered here. The builder corrects the comment's words to
     say so (a comment in `glass-shared`, no behaviour).
   - Why (a): the page holds no write yet. The writes are GG2f's and GG2g's.
8. **(a) The live Matrix.**
   - GG2d's `entityRows`, `linkRows`, `sortRows` and `pageOf` (moved to `glass-shared`) run over the store's
     `WorkingSetGraph`, drawn into GG2d's grid markup by the module. It makes no request but the sort's (item 9).
   - It carries three of the four canvas-bound `MATRIX_ACTIONS` ids GG2d left (`actionRegistry.ts:1337-1351`):
     `selection-carried-to-the-canvas`, `canvas-selection-carried-to-the-matrix` and
     `show-a-row-on-the-graph-by-keyboard`.
   - `expand-from-a-row-by-keyboard` is a write, so it is GG2f1's.
   - Why (a): with scripts on, the canvas is never the only carrier of the graph (`spec/02_GLASS_FRONTEND.md:2337-2346`).
9. **(a) The strength and rarity sort on the live Matrix** (`sort-links-by-strength-and-rarity-by-keyboard`, the
   registry's last Matrix id):
   - It uses `packages/glass-shared/src/strength/api.ts`, the client the workspace uses.
   - It calls `POST .../connection-strength` (`services/api/app.py:16132-16152`) and `POST .../rarity`
     (:16154-16175). Both need `INVESTIGATE` and the case's Viewer level (`test_route_rights.py:421-422`).
   - The calls go through the `/v1` forwarder with `X-CSRF-Token` (a `POST`; `apps/pages/server/csrf.ts:48`), once a
     sort is asked for, never on every delta.
   - A link with no figure sorts last and reads "no figure".
   - A refused or failed call takes the sort away and says why. Rarity's own `limit_exceeded` is said with the route's
     words, never as zeros.
   - Why (a): the decision record requires the sort in the Matrix, and here the routes answer for exactly the links
     drawn.

## What exists today (re-read at `b79164850`)

- `CANVAS_ACTIONS` has 65 ids (:87-203). `MATRIX_ACTIONS` has 12 (:1337-1351). `assertAllCovered` is at
  `actionRegistry.ts:69`. No `assertAllCovered` runs under `apps/pages/test` today. GG2b and GG2d each add one per
  spec, over the ids that spec's page offers.
- `connection_strength.py:82-84`: "a link named that is not in the working set … is left out". Rarity gives "no score
  (None)" for a pair outside it (:115-122).
- The live page, the store and the module are GG2e1's. The grid module and the moved rows are GG2d's. Neither is on
  main.

## Round 1's steps

1. Write GW's action and Matrix rows in `spec/08` and the acceptance test files first. Show them red on GG2e1's page:
   no actions wired, no Matrix.
2. Wire the actions of item 4 in `modules/graph/`. Each gets its case in `keyboard/live-graph.spec.ts`, with
   `assertAllCovered` over the ids the page offers. The spec lists the ids it does not offer and names the slice that
   will (GG2f1, GG2f2, GG2g1 to GG2g4, GG3d1, GG4i2 and GG4i3, as their briefs name them).
3. Draw the live Matrix (item 8) with GG2d's module, and keep it in step with the store.
4. Add the sort (item 9), its refusals and its cases.
5. Correct the registry comment (item 4). Run the checks and every plant.

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/live-graph-actions.test.ts` (vitest: the Matrix over a store fed by fixture
deltas, the sort's calls and refusals over a fixture forwarder that refuses as the routes do) and the Playwright
`OspreyFlow_Core/apps/pages/test/govuk/keyboard/live-graph.spec.ts` (both browsers), with GW's scenario test
`OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py` (GG2e1's, extended). All are red on main.

**The fixture forwarder refuses as the routes do** (rule 15): 403 without `investigate`, the case's 404 for a case the
reader may not open, and rarity's `limit_exceeded` past its cap.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | Each action of item 4 | reachable and working, one case per id | the id's key handler removed |
| 2 | `assertAllCovered` over the offered ids | green; red with one offered id's case removed | an offered id with no case |
| 3 | Select a node by keyboard | its label and type in the panel and the live region; never its id | the node's id announced |
| 4 | The live Matrix, a snapshot of 40 nodes, then a delta adding 3 | the Matrix holds 43, from the store; no request made | the Matrix built from a second read |
| 5 | Two readers of different clearance | each Matrix holds only its own stream's rows; no count beyond them | the rows read from the first reader's store (a module-level cache) |
| 6 | Selection carried both ways | a row selected selects the node, and back | the selection carried by node index, not id, so a delta shifts it |
| 7 | Show a row on the graph | the canvas focuses that node | the first node focused whatever the row |
| 8 | Sort links by strength | one `POST .../connection-strength` naming the drawn links; sorted, links with no figure last and said | a link with no figure sorted as zero |
| 9 | The sort refused (403), or the case gone (404) | the sort taken away, said in words; the Matrix kept | the refusal shown as an empty column |
| 10 | Rarity past its cap (`limit_exceeded`) | the route's words; no rarity sort | a partial sort of the first pairs |
| 11 | A sort asked, then three deltas | one call per sort asked, not one per delta | a call on every delta |
| 12 | The registry comment | says the pointer's pan, zoom and lasso are exempt; keyboard zoom registered | the comment left as it was (a words check over the file) |

## Checks

GG2e1's row's checks, with `npm test --workspace packages/glass-shared` (the comment and the moved rows).

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario GW's rows, after GG2e1's rows** in GW. GW itself sits after Scenario GV.

## Out of scope

- expanding from a row, seeding and expanding (GG2f1);
- every write (GG2f, GG2g);
- the inspector (GG3d1);
- metrics and strictness (GG4i2, GG4i3);
- any Conduit change;
- `apps/workspace`;
- the Default tree.

**Stop and ask** if a sort's figures would need a read beyond the two routes.

## Proposed `slices.tsv` row (not added)

```
GG2e2	GG2	The live graph page's read-only actions (zoom, fit, legend, focus ring, walking, the focused node announced, l through its links), each with its keyboard case, and the live Matrix over the store's graph carrying the selection both ways and sorting links by strength and rarity (ADR-139 decision 6); merges after WS4b (the owner's standing (a), D274; draft drafts_2026-11-28)	GG2e1,GG2d	2	lane/slice-GG2e2	full	OspreyFlow_Core/apps/pages/test/govuk/live-graph-actions.test.ts,OspreyFlow_Core/apps/pages/test/govuk/keyboard/live-graph.spec.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/live-graph-actions.test.ts && npm run test:govuk --workspace apps/pages -- keyboard/live-graph.spec.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2e2 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm test --workspace packages/glass-shared && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && node scripts/version_isolation_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2e2 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/glass_trees/test_version_isolation_check.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2e2 uv run --frozen ruff check .
```
