# Slice GG2b · GG2 · The canvas's first real page: a case's saved view drawn by the Sigma 4 graph module on the GOV.UK tree, read-only, with a paged table of the same graph for scripts off (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. No row in `slices.tsv`; no builder starts from this paper.

**Where it stands.** GG2a, the budget page, is ruled (`slices/GG2a.md`) and was to run as an away round only if PL7f
had merged by 13:00. **Neither `away/GG2a` nor `lane/slice-GG2a` exists** (refs read 25 November about 12:45 UTC), and
there is no `apps/pages/modules/graph/` or `apps/pages/test/perf/`. **GG2b needs GG2a merged and its result read:**
- if Sigma 4 meets the budget, GG2b draws with Sigma 4 and, by decision 9, "**may be written meanwhile, but it waits to
  merge**" until WS4 is in (`spec/06_DECISIONS.md` about lines 41101 to 41102; the correction of 19 November, about
  line 40973);
- if Sigma 4 does not meet the budget, `pages` falls back to Sigma 3 and "the owner is told before R4 goes on" (about
  lines 41103 to 41104). GG2b then waits for his word.

The scouts' cut of 20 November (`slices/STAGE4_SCOUTS_2026-11-20.md:86-88`) is GG2a the budget page, GG2b the working
set and delta client, GG2c the canvas actions, and GG2d the plain case list and Matrix tables, with b to d merging only
after WS4. **This draft proposes a different GG2b** (question 1).

## What exists today (read on 25 November 2026 at `4f77858a5`; re-read, lines move)

- **Reading a graph over HTTP: only a saved view.** `GET /v1/investigations/{id}/views/{view_id}` (`open_case_view`,
  `OspreyFlow_Core/services/api/app.py:4822-4848`) sits behind the case viewer gate. "The view re-read now, as this
  reader may see the case": `open_view` is run with the working set's cap (`cap_breach=_cap_breach`), and a merged
  drawing's annotations are read "through their own principal". It answers `CaseViewOpened`
  (`packages/schemas/case_views.py:130-143`): `view`, `nodes`, `edges`, `layout` (the saved positions of the items the
  reader may see), `missing` (only what was lost after the view was placed, "never what a marking hides", C045; SE7,
  SE9) and `annotations`. *The decorator names no `require_right`, where the board routes add `INVESTIGATE`; the
  builder confirms it against the route-rights table (`tests/services/api/test_route_rights.py`) and stops if it is a
  gap (rule 4).*
- **The case's live working set has no HTTP read.** The working set is built by `POST .../seed` (:5603, `INVESTIGATE`,
  editor), `POST .../expand` (:5673), `.../expand/preview` (:5745), `.../links-among` (:5707) and
  `working-set/add-by-ids` (:5636) and `add-by-identifiers` (:5767). It is read only through the delta WebSocket,
  `/v1/investigations/{id}/stream` (:21995): "on connect ... a full snapshot when the gap can't be proven closed ...
  filtered for this connection's own principal", with live deltas from Valkey (:21997-22006). The page service already
  forwards that upgrade with the bearer kept on the server (CO3: `apps/pages/server/stream.ts`, `attachStreamProxy`
  :160, frame and queue limits :89-92). **With scripts off, a page cannot hold a WebSocket**, so a live working set
  has no scripts-off form without a new HTTP read (decision 11 lists none).
- **The cap.** `services/api/working_set/models.py`: `MAX_NODES = 50_000` and `MAX_EDGES = 250_000` (:31-32);
  `LimitExceeded` (:50-65: `error: "limit_exceeded"`, `cap_kind`, `cap`, `would_be` and the three options
  `save_as_view`, `filter` and `promote_to_batch`, :42); `LimitExceededError` (:68). The React prompt's words are in
  `apps/workspace/src/canvas/CapRefusalPrompt.tsx` ("Too large to expand" :44, "Nothing has been added." :52, "Save a
  smaller view…" :56, "Run as a batch job" :61-64). `BatchExpansion.tsx` words it differently (NEXT_BATCH question 9).
- **The plain halves.** `packages/glass-shared/src/workingset/`: `store.ts` (225 lines that are not blank),
  `models.ts` (133) and `batchExpansionApi.ts` (157). **The delta client stayed in the workspace**
  (`apps/workspace/src/workingset/deltaClient.ts`, `connectDeltaClient` :97).
- **The page service.** Decision 1 (`spec/06` about lines 40986 to 40987): a module takes "its data from a JSON block in
  the page and its words from the markup". Both layouts carry the block (`<script type="application/json"
  id="page-data">`, `tree-govuk/layout.njk:30`, `tree-default/layout.njk:26`), holding only `{"page": …}` today; no
  module reads it yet. `modules/studio-frame.ts` (48 lines) is the one module. `scripts/assets.mjs:31` is
  `ALLOWED_DRAWING = []` and :33 the drawing pattern, refused at :182 (GG2a opens it for its module alone).
- **The canvas's keyboard.** `CANVAS_ACTIONS` has **65 entries** (`packages/glass-shared/src/keyboard/actionRegistry.ts:87-203`).
  Beside it are `CANVAS_CAP_ACTIONS` (:1391), `BATCH_EXPANSION_ACTIONS` (:1399) and `MATRIX_ACTIONS` (:1337).
- **The textual alternative.** `spec/02_GLASS_FRONTEND.md` about lines 2291 to 2296: the Matrix is "the
  screen-reader-navigable rendering of the same data ... Two HTML tables over the working set's own graph, no request of
  its own" (`apps/workspace/src/matrix/MatrixView.tsx`, 586 lines).
- **The budget.** `spec/02` §5 (about lines 2232 to 2265): first frame under 2.5 s, 60 fps pan and zoom, and the rest,
  at 50k / 250k; "The `pages` modules meet the same budget (ADR-152 I12) ... by `apps/pages/test/perf/`".
- **Scenarios.** The `graph-canvas` row (`FUNCTIONS.yaml:188-194`) names A9, A10, B5, B7 and B15 (`spec/08` rows about
  390, 391, 556, 558 and 566), all of them expansions and pivots, so all of them GG2c's. **None is a read-only view of a
  graph.**

## Questions for the owner (the proposal first)

1. **What GG2b is.** (a) **A saved view of a case, drawn read-only:** `/cases/{case_id}/views/{view_id}` in the GOV.UK
   tree. The server reads `GET .../views/{view_id}` once. With scripts on, GG2a's graph module draws the answer's nodes
   and links at the saved layout. With scripts off, **the same answer is a paged table** of its nodes and its links.
   This is the first page with real data, an HTTP read that already exists, and a scripts-off form, and it needs no
   delta client and no Conduit change. (b) The scouts' GG2b, the live working set through the stream with its delta
   client moved to `glass-shared`. That page has no scripts-off form (a WebSocket) and needs the delta client's move
   first. Proposed as GG2c, with expansion.
2. **How the module gets its data.** (a) **The module reads the view through the `/v1` forwarder** after the page loads
   (decision 3's latest-answer-wins guard), and the JSON block carries only the case's and view's ids and the words. A
   50k / 250k answer inlined in the HTML would be several megabytes to parse before the first frame (§5's 2.5 s). The
   server's own read is only for the scripts-off table. (b) Inline the answer in the JSON block, as decision 1 reads
   literally, measured against the budget first.
3. **The scripts-off table at 50,000 nodes.** (a) **Paged: 100 rows a page, "Nodes 1 to 100 of 4,213"** (the count is
   the route's own rows, which the reader may see), with page links, nodes and links as two tables. A page is never a
   silent slice (rule 2), and every row is reachable. (b) The Matrix's own two grids (GG2d), with GG2b waiting for
   them.
4. **The textual alternative while scripts are on.** (a) **The same paged tables, below the canvas, behind a GOV.UK
   "details" element** ("The graph as tables"), until GG2d's Matrix replaces them. A canvas is never the only carrier
   (the GR3a chart rule). (b) None until GG2d. Not proposed (spec/02's Matrix rule).
5. **Which canvas actions GG2b carries.** (a) **Read-only actions only**: pan, zoom, fit, move the focus from node to
   node by keyboard, and select a node to see its label and type in a plain panel. Each id is named from
   `CANVAS_ACTIONS` in the brief, with its keyboard case (rule 13, I7: `assertAllCovered` per tree's keyboard folder);
   the rest of the 65 are GG2c's. (b) Your list. NEXT_BATCH question 7 (unruled) asked the same.
6. **Past the cap.** (a) **The route's typed refusal, said with its three options in words** (the canvas prompt's
   wording as canonical: NEXT_BATCH question 9's proposal), each a link where a page exists and a sentence where none
   does. Neither the canvas nor the tables is drawn in part. (b) A sentence only.
7. **`missing`.** (a) **Shown in words only when the route sends more than zero** ("3 items in this view have been
   deleted since it was saved"). The page never computes it. (b) Not shown.
8. **The view's own right.** (a) **The builder confirms that `open_case_view` is in the route-rights table.** If it has
   no right beyond the viewer gate while the board routes add `INVESTIGATE`, it **stops and reports** (rule 4; the
   owner's). (b) Your word that the viewer gate is enough.
9. **Merging.** (a) **Built after GG2a has merged; merged only after WS4** (decision 9), with `VERSION_WINDOW.yaml`
   (WS4a) naming the window while it is open. (b) Your words.
10. **The scenario.** (a) **A new `spec/08` scenario, GV, written first and red first**, its id in the `graph-canvas`
    row for this page only. (b) Your words.

## The table of cases (each red first; planted faults at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A view of 40 nodes and 60 links, scripts on | the module's own ready mark set; the graph drawn at the saved positions; the "details" tables hold the same 40 and 60 | GG2a's readiness selector pointed at a mark never set (red: never ready), shown first |
| 2 | The same, scripts off | two tables: nodes (label, type) and links (from, type, to), the same items as the route sent | a link whose end is looked up outside the route's `nodes` |
| 3 | A view of 4,213 nodes, scripts off | "Nodes 1 to 100 of 4,213", page links, every row reachable by paging | the first 100 rows with no sentence (rule 2) |
| 4 | Two readers of different clearance over the leak test's world | the lower reader's canvas and tables hold only what the route sent them; no count beyond its rows | the module adding nodes from a second read |
| 5 | A view past the cap | the three options in words; no canvas, no table | a partial draw of the first nodes |
| 6 | `missing` above zero | the sentence of question 7 | the sentence drawn from a page-side count |
| 7 | A view of another person not shared, another case's view, a missing view, no level | the same 404 page, words and status | the route's 404 detail shown |
| 8 | The Conduit gives no answer, or 401 (for the server's read, and separately for the module's read through the forwarder) | the 502 "could not be read" page, or in the module a sentence in place of the canvas with the tables kept; a 401 says to sign in again | a blank canvas |
| 9 | A body missing a field `CaseViewOpened` requires | "could not be read", never an empty graph | each required field removed in turn |
| 10 | The budget at 50k / 250k on this page, with a fixture view | under the CI gate GG2a set (three runs, recorded with the machine); §5's numbers measured on the owner's Mac when he is back | the readiness red of case 1 |
| 11 | The bundle | `sigma` in the graph module's bundle alone; none in `glass-shared` (I13); no React (I1) | a planted `import "sigma"` in `glass-shared` |
| 12 | The policy | no `securitypolicyviolation` and no request to another origin (I2, I3) in Chromium and WebKit | a style attribute written by the module (decision 3 allows only the named CSSOM helper) |
| 13 | Keyboard | each action of question 5 reachable and working, a case per id; `assertAllCovered` red with an id left out | an id registered with no case |
| 14 | No internal id on the page | no node or link id in the HTML or the tables outside a link's own path | an id printed in a cell |

## Checks (frozen when cut)

The pages workspace tests, lint, typecheck, `no_react_check.mjs`, `version_isolation_check.mjs`, I20's check (WS4a's,
with the window listed); GG2a's perf spec and this page's (their own target); the GOV.UK keyboard and scripts-off
folders; the CSP spec for this page (I2, I3); `test_functions_yaml.py`, `test_tree_parity.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py`, `test_pages_setting.py`, `test_ui_words_check.py`, `test_doc_citations_check.py`;
`make licence-check`; `make -C OspreyFlow_Build design-check`; the cheap checks of 20 November. Every figure is
recorded with the machine it ran on, under the stack lease if it used the stack (rule 14).

## Out of scope

The live working set, the delta client's move and expansion (GG2c); the canvas actions beyond question 5 (GG2c); the
plain case list and the Matrix tables (GG2d); saving or sharing a view (GR1's saved views); any Conduit change; the
React workspace (WS4); a map layer (GG5).
