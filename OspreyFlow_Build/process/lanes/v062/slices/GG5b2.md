# Slice GG5b2 · GG5 · A saved view's places on a case map: MapLibre's own circles over the page service's basemap, read-only, with a table of the same places for scripts off

- **Build id:** GG5 (the `map-and-site-plans` row, `apps/pages/FUNCTIONS.yaml:393-399`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:**
  - GG5b1 (the module, glyphs and ranges);
  - GG2b (the view read and its strict reader, and the drawing modules in the production build);
  - GG2d (`defaultLabel` in `glass-shared`, so a place is named as the Matrix names it).

  **It merges after GG2b, so after WS4b.** It draws nothing with Sigma.
- **Split:** the second of GG5b's two parts (see GG5b1). GG5c's row (`after: GG5b,GG2b`) and GG5f's row mean this part.
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. No question here is the owner's.

## What

A reader opens **`/cases/map?case=<id>&view=<id>`** (the query form) and sees the saved view's located places on the
basemap. They are drawn as MapLibre's own circle layer, coloured by type and labelled with the place's name. Below
the map, and alone with scripts off, **a table of the same places**: name, type, and where it is in words ("51.5072 N,
0.1276 W"). GOV.UK page only.

**The answers (each (a), and why):**

1. **(a) A saved view's located places**, read-only. Why (a): no HTTP read gives a case's places outside a working set
   or a view (`POST .../map/places`, `services/api/app.py:9375-9404`, is the gazetteer's search, 2 to 100 characters,
   at most 25). The graph drawn over the map is GG5f's.
   - **Correction to the 26 November draft: a node's position is not in the view's answer.** As the workspace does it
     (`apps/workspace/src/map/geometries.ts:1-100`):
     - a node is placed when its type is placeable: `Location`, and every type the ontology declares a `geometry_ref`
       on (`placeableTypes`, :28);
     - its `geometry_ref` resolves through `POST /v1/analytics/geometries` (`app.py:10123-10142`): `INVESTIGATE`,
       audited `analytics_geometries`, read under the principal (`analytics.get_geometries(..., principal)`);
     - a node whose reference does not resolve is absent, "not dimmed".
   - So the server half makes three reads per render: GG2b's view read; `GET /v1/ontology` (`app.py:9333`, the types'
     `geometry_ref` and channels); and one `POST /v1/analytics/geometries` for the view's unique references, through
     `glass-shared`'s `fetchGeometries` (`packages/glass-shared/src/analytics/api.ts:98`).
   - `placeableTypes`, `geometryRefOf` and the reference-collecting step move to `packages/glass-shared/src/map/`,
     behaviour unchanged (I11). The step takes a node list beside the workspace's `WorkingSetGraph`.
2. **(a) The look: circles coloured by type from the tokens** (`--ch-<channel>`, the channel the ontology names for the
   type), **labelled as the Matrix names them** (GG2d's `defaultLabel`; a node with no name is said as its type). This
   is not the workspace's Sigma drawing. Why (a): I6 is about functions, not looks, and the Sigma look over the map is
   GG5f's.
8. **(a) The cap.** A view past the cap is GG2b's typed refusal, said with the same three options in words. No map is
   drawn and no table. Why (a): rule 2.

## What exists today (re-read at `b79164850`)

- The view route, the cap and the strict reader are GG2b's. The module, glyphs and ranges are GG5b1's. Neither is on
  main.
- **The "basemap not built" 404** names a server path in its detail: "basemap not built — {path} does not exist yet"
  (`app.py:9591-9596`). The page must never show it.
- `MAP_VIEW_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:992-998`):
  - `switch-the-basemap-by-keyboard`;
  - `find-a-place-by-keyboard`;
  - `add-a-gazetteer-by-keyboard` and `remove-a-gazetteer-by-keyboard` (GG5d's).

  This page offers none of them. The map's own zoom buttons and the table are its keyboard surface.
- **GG5c** (`slices/GG5c.md:89-91`) expects the server half to read once per render and hand the module its data "as
  GG5b gives it the places". So this part gives the module the places through the JSON block (decision 1), never by a
  second read from the browser.

## Round 1's steps

1. Write Scenario MP's case-map rows (after GG5b1's) and the acceptance test files first. Show them red on main: no
   page.
2. **Add the row and the lists.**
   - The `map-and-site-plans` row gains slice "GG5b2" and MP's ids. Its route stays empty until I8.
   - Add one import and one `PAGES` line, and `/cases/map` at the end of `routes.yaml`.
   - Add `test_govuk_case_map_scenario` to `test_route_pins.py`'s `SCENARIO_TESTS`.
3. **Move the plain geometry steps** (item 1), with the workspace's `geometries.test.ts` green and unchanged but for
   imports.
4. **Build the server half.** Write `server/caseMap.ts` (`caseMapPage`: id `map-and-site-plans`, path `/cases/map`,
   GET, `trees: ["govuk"]`), `server/views/caseMapWords.ts` and `tree-govuk/case-map.njk`.
   - It makes the three reads.
   - It writes the places, with no ids, into the JSON block.
   - It draws the table.
   - It uses one 404 page for every refusal.
5. **Build the module half:** GG5b1's `mountMap` with a circle layer and a label layer over the JSON block's places,
   the camera fitted to them, and the basemap's own centre when there are none.
6. Run the checks and every plant.

## Acceptance test (new, red on main)

All three are red on main:
- `OspreyFlow_Core/apps/pages/test/govuk/case-map.test.ts` (vitest; the server half and the moved steps);
- `OspreyFlow_Build/tests/glass_trees/test_govuk_case_map_scenario.py` (MP's rows, the row, the census of
  `GeometryRecord` and the view's fields, its own path once);
- `OspreyFlow_Core/apps/pages/test/govuk/case-map.spec.ts` (Playwright, both browsers).

The fixture Conduit refuses as the routes do: `geometries` without `investigate` is a 403, and a reference the reader
may not see is left out, as `get_geometries(..., principal)` leaves it.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | A view with 12 located places and 5 not placeable, scripts on | the map reaches `idle` with the basemap and 12 circles; the table of 12 | the readiness check on an event that never fires, shown first |
| 2 | The same, scripts off | the table of 12, whole, each place's position in words | the table drawn only by the module |
| 3 | A `Person` carrying a `geometry_ref` its type does not declare | not placed (`placeableTypes`' rule) | every node with a `geometry_ref` placed |
| 4 | A reference that does not resolve | absent, not dimmed, not counted | a circle at 0, 0 |
| 5 | Two readers of different clearance | each map and table holds only what their own reads sent | the render cached by case and view, not by session |
| 6 | One render | exactly one view read, one ontology read, one geometries call with the unique references | a geometries call per node |
| 7 | A basemap not built (the route's 404) | "The map's basemap has not been built" in the page's own words; the table whole | the route's detail shown (a server path on the page) |
| 8 | No located place | "Nothing in this view has a map position"; the basemap at its own centre | a camera fitted to an empty box |
| 9 | A view past the cap | GG2b's three options in words; no map, no table | the first places drawn (rule 2) |
| 10 | A view of another person not shared, another case's, missing, no level | the same 404 page | the route's detail shown |
| 11 | Colours and names | each circle's colour a `--ch-*` token by the ontology's channel; names from `defaultLabel`; a nameless place said as its type | a hex value in the layer's paint |
| 12 | Keyboard and scripts off | the map's zoom buttons and the table reachable in order (rule 13, I4) | a control taken out of the tab order |
| 13 | No internal id | no node id or `geometry_ref` in the HTML or the JSON block | a reference written into the block |
| 14 | The moved steps (I11) | the workspace's map tests green, unchanged but for imports | a relative import of the old path left behind |
| 15 | The page's own path | `/cases/map` once in the route list | the path listed twice |

## Checks

GG2b's row's checks, with `test_govuk_case_map_scenario.py`, `npm test --workspace packages/glass-shared` and `npm test
--workspace apps/workspace` (the moved steps), and I20's check.

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario MP's case-map rows, after GG5b1's rows** in MP. MP itself sits after
Scenario TS.

## Out of scope

- heat and hotspots (GG5c);
- boundaries and gazetteers (GG5d);
- site plans (GG5e);
- the graph on the map (GG5f);
- the live working set on a map;
- switching the basemap;
- any Conduit change;
- `apps/workspace` beyond import lines;
- the Default tree.

**Stop and ask** if placing a node needs a read the workspace does not make, or if the geometries route could return a
reference the reader may not see.

## Proposed `slices.tsv` row (not added)

```
GG5b2	GG5	A saved view's places on a case map at /cases/map?case=…&view=…: placeable types (Location and every type declaring geometry_ref) resolved through POST /v1/analytics/geometries, drawn as MapLibre circles by the ontology's channel tokens and named as the Matrix names them, with a table of the same places for scripts off; the plain geometry steps moved to glass-shared (I11); merges after GG2b (so after WS4b) (the owner's standing (a), D274; draft drafts_2026-11-28)	GG5b1,GG2b,GG2d	2	lane/slice-GG5b2	full	OspreyFlow_Core/apps/pages/test/govuk/case-map.test.ts,OspreyFlow_Core/apps/pages/test/govuk/case-map.spec.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_case_map_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/case-map.test.ts && npm run test:govuk --workspace apps/pages -- case-map.spec.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG5b2 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_case_map_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm test --workspace packages/glass-shared && npm test --workspace apps/workspace && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && node scripts/version_isolation_check.mjs && node scripts/same_drawing_versions_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG5b2 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_case_map_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/glass_trees/test_version_isolation_check.py ../OspreyFlow_Build/tests/glass_trees/test_glass_shared_plain_logic.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG5b2 uv run --frozen ruff check .
```
