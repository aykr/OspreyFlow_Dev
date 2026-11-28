# Slice GG2b · GG2 · A case's saved view on the GOV.UK tree, drawn read-only by the Sigma 4 graph module, with the same graph as paged tables

- **Build id:** GG2 (a new `saved-view` row of `apps/pages/FUNCTIONS.yaml`; the plan's GG2b, `drafts_2026-11-26/CHAIN_PLAN.md:62`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:** GG2a (the graph module and `DRAWING_MODULES`, on `away/GG2a` `759a45233`, not merged). GR1a is merged.
  **Its merge waits for WS4b** (ADR-152 decision 9: "The rest of R4 may be written meanwhile, but it waits to merge",
  `spec/06_DECISIONS.md:41101-41102`; only GG2c has the owner's exception, 26 November about 10:35 UTC). It may be
  written meanwhile.
- **Status:** a brief written in an away drafting session (D246, D295), 28 November 2026, on `drafts/2026-11-28`, read
  from `origin/main` at `b79164850` and from `away/GG2a`. Re-read every line before cutting. **One item waits for the
  owner before the merge (not before the start):** O1 in `INDEX.md` (GG2a's "never served" test).

## What

A reader opens one of a case's saved views at **`/cases/views?case=<id>&view=<id>`** (the query form, GR1a question 1
(a)). The server reads `GET /v1/investigations/{id}/views/{view_id}` once. With scripts on, GG2a's graph module draws
the answer's nodes and links at their saved places. With scripts off, and below the canvas when scripts run, **the same
answer is two paged tables**, nodes and links. GOV.UK page only; no Default-tree twin.

This brief carries the 25 November draft's proposals, each (a) by the owner's ruling of 26 November (about 10:35 UTC:
"the 25 November drafts with the 26th's corrections"), with these corrections:

1. **(a) A saved view, read-only.** It is the first page with real graph data. It uses an HTTP read that already
   exists, it has a scripts-off form, and it needs no delta client and no Conduit change.
2. **(a) The module reads the view itself, through the `/v1` forwarder** (decision 3's latest-answer-wins guard). The
   JSON block (`<script type="application/json" id="page-data">`, `tree-govuk/layout.njk:30`) carries only the case's
   and view's ids and the words. Why (a): an answer of 50,000 nodes and 250,000 links inlined in the HTML is megabytes
   to parse before §5's first frame (`spec/02_GLASS_FRONTEND.md:2285`).
3. **(a) Paged tables: 100 rows a page, "Nodes 1 to 100 of 4,213".** The count is the rows the route sent. Page links
   reach every row. Why (a): rule 2, never a silent slice.
4. **(a) The same tables below the canvas, in a GOV.UK `details` element "The graph as tables",** until GG2d's Matrix
   replaces them. The owner ruled the Matrix GG2d's (26 November). Why (a): a canvas is never the only carrier.
5. **(a) Read-only canvas actions only, each named by id** from `CANVAS_ACTIONS`
   (`packages/glass-shared/src/keyboard/actionRegistry.ts:87-203`, 65 ids), each with its keyboard case (rule 13):
   - `zoom-in-and-out-by-keyboard` (:88) and `fit-to-view-by-keyboard` (:89);
   - `focus-establishes-ring` (:97), `tab-leaves-the-canvas` (:98), `ctrl-arrow-cycles-ring` (:99);
   - `ctrl-shift-arrow-walks-every-node` (:106), `arrow-walk-forward` (:107), `arrow-walk-backward` (:108);
   - `focused-node-is-announced` (:110).

   Selecting a node shows its label and type in a plain panel. The rest are GG2e2's, GG2f's and GG2g's. Why (a): a
   saved view is a snapshot, and nothing on it writes.
6. **(a) Past the cap, the route's typed refusal is said with its three options in words.** The options are
   `save_as_view`, `filter` and `promote_to_batch` (`services/api/working_set/models.py:44-48`). The words are the
   canvas prompt's (`apps/workspace/src/canvas/CapRefusalPrompt.tsx:44`, :52, :56, :61-63). Nothing is drawn in part:
   no canvas and no table. Why (a): rule 2.
7. **(a) `missing` is said only when the route sends more than zero.** Today `CaseViewOpened.missing` is 0 for every
   reader "until the store records deletions" (`packages/schemas/case_views.py:131-134`), so the sentence is proved on
   a body the schema allows, and the page never computes a count. Why (a): rule 7, no count the route did not send.
8. **Closed by the code.** The route-rights table records `"open_case_view": None`
   (`OspreyFlow_Build/tests/services/api/test_route_rights.py:77`), and `app.py:4791` says that listing and opening
   "need only the level". The route is `app.py:4884-4912`. There is no gap to stop on.
9. **Merging after WS4b** is decision 9, not a choice (see *After*).
10. **(a) A new scenario GV, written first and red first.**

**Who saved the view is left out** (the owner, 26 November: "who made it" is left out for 0.7.0). The census names
`CaseView`'s author field as left out.

## What exists today (re-read at `b79164850`)

- **The route** `open_case_view` (`OspreyFlow_Core/services/api/app.py:4884-4912`):
  - It sits behind the case's level and names no right.
  - It runs `open_view` with the working set's cap (`cap_breach=_cap_breach`, :4900-4901).
  - It reads a merged drawing's annotations through their own principal (:4905-4906).
  - It answers `CaseViewOpened` (`packages/schemas/case_views.py:130-143`): `view`, `nodes`, `edges`, `layout`,
    `missing` and `annotations`. Each field is `extra="forbid"`.
- **The cap:** `MAX_NODES = 50_000` and `MAX_EDGES = 250_000` (`working_set/models.py:32-33`), `LimitExceeded`
  (:51-66), and `LimitExceededError` (:69).
- **The graph module is not on main.**
  - On `away/GG2a`, `apps/pages/modules/graph/index.ts` exports `mountGraph(container, data, options)` (:88),
    `READY_ATTRIBUTE = "data-graph-state"` (:50) and `READY_MARK` (:53). It pins `sigma` 4.0.6 and `graphology` 0.26.0.
  - `scripts/assets.mjs` there adds `DRAWING_MODULES = { graph: ["sigma"] }` (:44) and `buildDrawingModule` (:303).
    `buildAssets` never builds a drawing module (:20-21), "so no page and no production build carries it".
  - GG2a's `test/server/budgetPageNotServed.test.ts` holds three things: no page whose path or id matches
    `/graph|budget|perf/i`; no route-list path that does; and no Sigma in any file of the production build.
  - **GG2b's page needs the module in the production build**, and GG2e's `/cases/graph` matches that pattern (O1).
- **On main:** `scripts/assets.mjs:31` has `ALLOWED_DRAWING = []`, and `modules/` holds `studio-frame.ts` alone.
- **Keyboard:** no `assertAllCovered` runs under `apps/pages/test`. The function is at `actionRegistry.ts:69`, and the
  workspace's pattern is `apps/workspace/keyboard/matrix.spec.ts:238-239`. The GOV.UK keyboard and scripts-off folders
  are `apps/pages/test/govuk/keyboard/` and `apps/pages/test/govuk/scripts-off/`.
- **The policy spec:** the only one is GG5a's `apps/pages/test/csp/map.spec.ts` (`npm run test:csp`). Its CI patch is
  not applied (`away/GG5a_AWAY_REPORT.md:245-249`).
- **The page lists:**
  - `server/pageList.ts` and `tree-govuk/routes.yaml` take git's union merge (`.gitattributes`, hand-back 66).
  - A page adds one import line, one `PAGES` line and one route line, and edits none.
  - Each page's scenario test checks its own path, once. `tests/glass_trees/test_route_pins.py` keeps it so, over
    `SCENARIO_TESTS` (:26-34).
- **`FUNCTIONS.yaml`:** one page per row per tree (`server/pages.ts`'s `checkTree`). `cases-and-views` is the case
  page's (`server/cases.ts:239`), so a view page needs a row of its own, as GR4a's trends page got one.
  `test_functions_yaml.py:70` has `EXPECTED_FUNCTIONS = 50`.

## Round 1's steps

1. **Take GG2a in.** If GG2a has merged, work from main. If not, stop: the conductor starts GG2b only after GG2a's merge.
2. **Write the scenario first.** Write `spec/08` Scenario GV (placement below) and the acceptance test files. Show
   them red on main: there is no page and no row.
3. **Add the row and the lists.** Add the `FUNCTIONS.yaml` row `saved-view` (name "A saved view, drawn read-only, and
   its graph as tables", slice "GG2b", scenario GV's ids, route empty until I8) and `EXPECTED_FUNCTIONS = 51`. Add one
   import and one `PAGES` line to `pageList.ts`, and `/cases/views` at the end of `routes.yaml`. Add
   `test_govuk_saved_view_scenario` to `test_route_pins.py`'s `SCENARIO_TESTS`.
4. **Build the server half.** Write `server/savedView.ts` (`savedViewPage`: id `saved-view`, path `/cases/views`, GET,
   `trees: ["govuk"]`), `server/views/savedViewWords.ts` and `tree-govuk/saved-view.njk`.
   - It makes one Conduit read per render.
   - It reads strictly: a body missing a field `CaseViewOpened` requires is "could not be read", never an empty graph.
   - It draws both tables, paged by `?nodes=<n>` and `?links=<n>` (page numbers, never ids).
   - It uses one 404 page for every refusal and for a missing view.
5. **Build the module half.**
   - The production build carries the `DRAWING_MODULES` bundles: `buildAssets` calls `buildDrawingModule` for each.
   - Sigma stays allowed only in `modules/graph`'s bundle, and a planted Sigma import in any other bundle is still
     refused (`bundleRules.test.ts`).
   - The view page alone loads the graph bundle, with the page's nonce.
   - The module reads the view through `/v1`, applies the latest-answer-wins guard, draws at `layout`, sets
     `READY_ATTRIBUTE` and wires the actions of item 5.
6. **Narrow GG2a's test, only as O1 (a) words it** (red first): the budget page and the perf harness are still never
   served. If the owner rules O1 otherwise before the merge, follow his words.
7. **Add the browser cases** (`keyboard/`, `scripts-off/`, `test/csp/`, `test/perf/`).
8. **Run the checks and the cases' plants.** Record every figure with the machine it ran on (rule 14).

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/saved-view.test.ts` (vitest, the server half and the module's pure parts) and
`OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py` (GV's rows, the row, the field census, its own
path once). Both are red on main: no page, no row, no scenario. The browser cases are in
`apps/pages/test/govuk/saved-view.spec.ts`, `keyboard/saved-view.spec.ts`, `scripts-off/saved-view.spec.ts`,
`test/csp/saved-view.spec.ts` and `test/perf/saved-view.spec.ts`. The merge's full gate runs them; `saved-view.spec.ts`
is in the acceptance command.

| # | Case | Expected | The planted fault that shows it red (rule 15, at the real call site) |
| --- | --- | --- | --- |
| 1 | A view of 40 nodes and 60 links, scripts on | the module's ready attribute set; the graph at the saved places; the tables hold the same 40 and 60 | the readiness selector pointed at a value never set (never ready), shown first |
| 2 | The same, scripts off | two tables: nodes (label, type) and links (from, type, to), the route's items | a link's end looked up outside the route's `nodes` |
| 3 | A view of 4,213 nodes, scripts off | "Nodes 1 to 100 of 4,213", page links, every row reachable | the first 100 rows with no sentence (rule 2) |
| 4 | Two readers of different clearance over the leak test's world | each reader's canvas and tables hold only what the route sent that reader; no count beyond its rows | the page's render keyed by the view, not the session (the second reader served the first's answer) |
| 5 | A view past the cap (the route's `limit_exceeded`) | the three options in words; no canvas, no table | the first nodes drawn (rule 2) |
| 6 | `missing` of 3 (a body the schema allows) | "3 items in this view have been deleted since it was saved"; with 0, no sentence | the sentence drawn from a page-side count |
| 7 | Another person's view not shared, another case's view, a missing view, no level | the same 404 page, words and status | the route's 404 detail shown |
| 8 | The Conduit gives no answer, or 401 (the server's read, and separately the module's read) | the 502 "could not be read" page; in the module, a sentence in place of the canvas with the tables kept; 401 says sign in again | a blank canvas |
| 9 | A body missing a field `CaseViewOpened` requires | "could not be read", never an empty graph | each required field removed in turn, from the model's own field list |
| 10 | The budget at 50,000 / 250,000 on this page (a fixture view) | under GG2a's CI gate, three runs recorded with the machine | case 1's readiness red |
| 11 | The bundles | `sigma` only in the graph bundle; none in `glass-shared` (I13); no React (I1); only the view page loads the bundle | a planted `import "sigma"` in a page module, and in `glass-shared` |
| 12 | The policy | no `securitypolicyviolation` and no request to another origin (I2, I3), Chromium and WebKit | a style attribute written by the module (decision 3 allows only the named CSSOM helper) |
| 13 | Keyboard | each id of item 5 reachable and working, one case per id; the spec's `assertAllCovered` over the offered ids red with one removed | an offered id with no case |
| 14 | No internal id in the HTML | no node or link id in the markup or tables, outside the module's own JSON read and a link's query | an id printed in a cell |
| 15 | The page's own path | `/cases/views` in the route list once; a new page beside it changes nothing in this test | the path listed twice |
| 16 | GG2a's test after O1 (a) | the budget page still unserved: the perf harness's page in no list, `test/perf` in no built file | the budget page's own module named in `PAGES` |

## Checks

The pages workspace tests, lint, typecheck, `no_react_check.mjs` and `version_isolation_check.mjs`; the GOV.UK
scenario tests; `test_route_pins.py` and `test_page_lists_merge.py`; `test_functions_yaml.py`,
`test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`,
`test_version_isolation_check.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py` and
`tests/harness/test_pages_setting.py`; `ruff check .`. All pure, store ports pinned to 9. The browser specs, `make
licence-check` and `design-check` run in the merge's full gate.

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: a new **Scenario GV — A case's saved view drawn read-only, and its graph as tables
(slice GG2b, GOV.UK tree)**, **after Scenario AQ** (the alert queue, `## Scenario AQ` at :1016) and before Scenario S.
GG2d adds its Matrix rows to GV.

## Out of scope

- the live working set (GG2e1);
- the read-only actions on the live page (GG2e2);
- the Matrix (GG2d);
- seeding and expanding (GG2f);
- the editing actions (GG2g);
- saving, sharing or deleting a view (GR1d);
- a map (GG5b);
- any Conduit change;
- `apps/workspace`;
- the Default tree.

**Stop and ask** if GG2a merges with a different module export, if the forwarder cannot carry the view's answer, or if
anything would draw part of a view.

## Proposed `slices.tsv` row (not added)

```
GG2b	GG2	A case's saved view at /cases/views?case=…&view=…, drawn read-only by GG2a's Sigma 4 module with its graph as paged tables (scripts off and below the canvas); a new saved-view row; merges after WS4b (decision 9); WAITS FOR THE OWNER before its merge: O1, GG2a's never-served test narrowed to the budget page (the owner's standing (a), D274; draft drafts_2026-11-28)	GG2a	2	lane/slice-GG2b	full	OspreyFlow_Core/apps/pages/test/govuk/saved-view.test.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/saved-view.test.ts && npm run test:govuk --workspace apps/pages -- saved-view.spec.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2b uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && node scripts/version_isolation_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2b uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/glass_trees/test_version_isolation_check.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2b uv run --frozen ruff check .
```
