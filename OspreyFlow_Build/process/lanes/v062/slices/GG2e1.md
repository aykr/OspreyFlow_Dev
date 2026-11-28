# Slice GG2e1 · GG2 · The case's live working set on a GOV.UK page: the graph module fed by the delta stream through the page service, drawn, with a sentence and the case's saved views when scripts are off

- **Build id:** GG2 (the `working-set` row of `apps/pages/FUNCTIONS.yaml:197-203`: "Working set, delta stream, cap
  refusal, batch expansion")
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:** GG2b (the graph module in the production build, and a page that draws it); GG2c (the delta client in
  `glass-shared`, from `away/GG2c`, not merged). CO3 (the stream proxy) is merged. **Its merge waits for WS4b**
  (decision 9: it draws with Sigma). It may be written meanwhile.
- **Split, as the 26 November draft proposed (its question 1 (a)):** GG2e is size L, so it is two parts. **GG2e1 (this
  part)** covers the subscription, the drawing, the cap frame, the socket's end, the scripts-off sentence and the
  budget. **GG2e2** covers the read-only actions and the live Matrix.
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. **The parity line is the owner's to apply:** `GG2e1_PARITY_LINE.diff` beside this brief (question 2,
  already ruled (a); its exact words are his). The merge waits for it to be applied.

## What

A reader of a case opens **`/cases/graph?case=<id>`** (the query form, GR1a question 1 (a)). With scripts on:
1. The page's module opens the case's stream through the page service's proxy (CO3).
2. It applies the snapshot and the deltas to GG2c's store (`zustand/vanilla` over graphology,
   `packages/glass-shared/src/workingset/store.ts`).
3. It draws the store's graph with GG2a's `mountGraph`.

A change made anywhere, in the React workspace or by another reader, reaches the page without a reload. Each reader
sees only their own projection (`services/api/working_set/service.py:6-9`, :11-24). With scripts off, the page says in
words that the live graph needs scripts. It lists the case's saved views as links to GG2b's pages, which draw each view
as tables. GOV.UK page only.

**The answers (each (a) unless ruled, and why):**

1. **The split: (a)** (see above). Why: one part a round.
2. **Scripts off: ruled (a), "a parity line"** (the owner, 26 November about 10:35 UTC).
   - The line is in `GG2e1_PARITY_LINE.diff`, a new class `scripts-off-live-working-set`.
   - The existing `scripts-off-drawn-canvas` line (`apps/pages/PARITY_EXCEPTIONS.yaml:45-48`) does not cover this page.
     Its condition is "a table takes the place of the graph", and no HTTP read of the working set exists (every
     working-set route is a `POST`, `app.py:5665-5829`), so no table can.
   - The page lists the case's saved views itself, with one `GET .../views` per render (`list_case_views`,
     `app.py:4794`), as links to `/cases/views?case=…&view=…`. So the line's words hold without waiting for GR1d.
3. **The address: `/cases/graph?case=<id>`**, the ruled query form. GR1c is withdrawn.
4. **(GG2e2's.)**
5. **(a) The cap on the stream.** A `DeltaViewOverCap` frame is "sent in place of a snapshot, with no graph content"
   (`glass-shared/src/workingset/models.ts:91-99`; it is outside the `WorkingSetDelta` union, :101). It is said with
   its three options in the canvas prompt's words. The graph is left as it was: nothing cleared, nothing drawn in
   part. Why (a): rule 2.
6. **(a) A socket that ends.**
   - The proxy's refusals (another path 404, a foreign `Origin` 403, no session 401, a store that cannot be read 503)
     are handshake answers that browser code cannot read (`apps/pages/server/stream.ts:15-20`, code :306, :315,
     :320-332, :344). Every Conduit refusal before accept reaches the browser as 1008 (:26-36, :263).
   - On a failure to open, or a 1008, the module asks the page service whether the session stands, with one plain
     same-origin `GET` of a page it already serves, which redirects to sign-in when the session has ended.
   - It says "Sign in again" only then. Otherwise it says "The live graph could not be reached. Try again", with one
     retry, never a loop.
   - Why (a): the page must not tell a person to sign in when the Conduit is down.
7. **(a) The figures.** GG2a's perf harness runs over this page at 50,000 / 250,000, with a snapshot of that size from
   a fixture stream, under GG2a's CI gate. Three runs, recorded with the machine. Why (a): this page's first frame is
   the snapshot's, which GG2a did not measure.

**Who changed what** is not shown (the owner, 26 November: who made it is left out for 0.7.0).

## What exists today (re-read at `b79164850`)

- **The stream** `@app.websocket("/v1/investigations/{investigation_id}/stream")` (`OspreyFlow_Core/services/api/app.py:22138`):
  - On connect, it sends "exactly what `WorkingSetService.sync` decides — the missed deltas, or a full snapshot",
    filtered for the connection's own principal (docstring :22140-22149). Live deltas come from Valkey (:22146-22148).
  - Its own refusals: an unresolvable principal, 1008 (:22152-22154); the principal store down, 1013 (:22155-22157);
    a principal admitted to named routes alone, 1008 (ADR-148 Amendment 10, :22158-22163); a ticket no longer in
    standing (Amendment 8, :22164-22167); a case the principal may not read, 1008 (:22175-22185).
- **The proxy** (`apps/pages/server/stream.ts`):
  - `STREAM_PATH` (:86) is `/v1/investigations/<id>/stream` on the page's own origin, and `attachStreamProxy` is at
    :160.
  - It sends the person's bearer upstream (:210-211).
  - A browser frame is at most 1 MiB (:89, `maxPayload` :171), and at most 1 MiB may queue before upstream opens (:91;
    an overflow closes with 1009, :281-284).
  - The forwarder refuses to carry the stream over HTTP (`forward.ts:97-101`).
- **The X2 tests of decision 11** are vitest `describe` blocks in `apps/pages/test/server/stream.test.ts`:
  `test_the_stream_through_pages_carries_only_what_the_person_may_read` (:509),
  `test_an_upgrade_from_another_origin_is_refused_by_pages` (:753) and
  `test_a_bearer_in_the_url_is_still_refused_through_pages` (:788). They run in `npm test --workspace apps/pages`.
- **The delta client is not in `glass-shared` on main.** It is at `apps/workspace/src/workingset/deltaClient.ts`
  (`connectDeltaClient` :97). GG2c moves it, with "no browser socket factory yet" (`slices/GG2c.md:8-11`). **GG2e1
  writes the browser's socket factory in the page's module, not in `glass-shared`.**
- **Bundling:**
  - `scripts/assets.mjs` on main bundles only `.ts` files directly in `modules/` (:13, :209-215); a folder is skipped
    silently.
  - The graph module is a drawing-module folder built by GG2a's `buildDrawingModule`, which GG2b puts in the
    production build.
  - **GG2e1 adds its live boot to that module.** The module reads the JSON block's `page` value (decision 1) and boots
    the view (GG2b) or the live graph (GG2e1). There is one bundle, and Sigma stays allowed only there.
- **The later briefs that build on this page:** GG2f1 (`slices/GG2f1.md:14`, :82), GG3d1 (:69-70) and GG4i2 (:48).
  Each assumes `/cases/graph?case=…` and `apps/pages/modules/graph/`, which this brief keeps.

## Round 1's steps

1. Write `spec/08` Scenario GW and the acceptance test files first. Show them red on main: no page.
2. **Add the row and the lists.**
   - The `working-set` row gains slice "GG2e1" and GW's ids. Its route stays empty until I8.
   - Add one import and one `PAGES` line to `pageList.ts`, and `/cases/graph` at the end of `routes.yaml`.
   - Add `test_govuk_live_graph_scenario` to `test_route_pins.py`'s `SCENARIO_TESTS`.
3. **Build the server half.**
   - Write `server/liveGraph.ts` (`liveGraphPage`: id `working-set`, path `/cases/graph`, GET, `trees: ["govuk"]`),
     `server/views/liveGraphWords.ts` and `tree-govuk/live-graph.njk`.
   - It makes one `GET .../views` per render for the scripts-off list, and one case read for the gate.
   - A case the reader may not open gets one 404 page.
4. **Build the module half**, in `apps/pages/modules/graph/`:
   - the browser socket factory, on the page's own origin and `STREAM_PATH`;
   - GG2c's client over it, the store, and `mountGraph` over the store's graph;
   - the cap frame (item 5), the session check (item 6) and the ready attribute.
5. **Plant the parity line in the test only.** Add the class to `SCRIPTS_OFF_CLASS`, red first. The line itself goes
   in when the owner applies the diff. Until then the scripts-off case checks the page's words and links, and
   `test_tree_parity.py` is not asked to call the tree complete.
6. Add the browser cases (`live-graph.spec.ts`, `scripts-off/`, `test/csp/`, `test/perf/`). Run the checks and every
   plant. Record figures with the machine they ran on.

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/live-graph.test.ts` (vitest: the server half, the boot's choice, the socket
factory, the frame handling over a fake socket that refuses as the proxy does) and
`OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py` (GW's rows, the row, its own path once), with
the Playwright `apps/pages/test/govuk/live-graph.spec.ts` (both browsers, a fixture Conduit stream behind the real
proxy) in the acceptance command. All three are red on main.

**The fixture stream models the Conduit's refusals, not only its grants** (rule 15's second example). It closes with
1008 for an unknown principal and for a case the person may not read, and with 1013 for a store outage. It opens
nothing before the proxy's own `Origin` and session checks pass.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | Connect, a snapshot of 40 nodes | drawn, the ready attribute set (GG2a's) | the readiness selector pointed at a value never set |
| 2 | A seed made through the fixture Conduit while the page is open | its nodes appear without a reload | the module reading only the first frame |
| 3 | A delta whose `seq` skips one | the resync asked (`last_acknowledged_seq`); the graph equal to the server's after | GG2c's gap check bypassed |
| 4 | Two readers of different clearance | each page holds only what its own stream sent | a shared upstream socket in the proxy (the second person's page served the first's frames) |
| 5 | An upgrade from another origin | refused by the proxy before any upgrade; the page's own socket unaffected | the proxy's `Origin` check removed |
| 6 | The session ends while connected; separately, the store is down (1008 and 1013) | "Sign in again" only for the first; "could not be reached" for the second; one retry, no loop | "Sign in again" on every close |
| 7 | `DeltaViewOverCap` | the three options in words; the graph left as it was | the frame treated as an empty snapshot (the graph cleared) |
| 8 | Scripts off | the sentence; the case's saved views as links to `/cases/views?case=…&view=…`, by name; none of them when the case has none, with "This case has no saved views" | an empty canvas and nothing else |
| 9 | A case the reader may not open | the same 404 page as a missing case | the stream opened and refused after the page drew |
| 10 | No internal id in the HTML or a live region | none; a view's id only in its link's query | a node id announced |
| 11 | The policy | no `securitypolicyviolation`; no request to another origin (I2, I3); the socket same-origin | a socket opened to the Conduit's own address |
| 12 | The budget | under GG2a's CI gate, three runs, recorded | none: a measurement, red first by case 1's readiness |
| 13 | The parity class | `SCRIPTS_OFF_CLASS` accepts `scripts-off-live-working-set`; an unknown class is still refused | the class added and the refusal test removed |
| 14 | The page's own path | `/cases/graph` once in the route list | the path listed twice |

## Checks

GG2b's row's checks, with `test_govuk_live_graph_scenario.py` in place of the saved view's, and `npm test --workspace
packages/glass-shared` (the client GG2c moved).

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: a new **Scenario GW — The case's live working set on a page (slices GG2e1 and GG2e2,
GOV.UK tree)**, **after Scenario GV** (GG2b's, which sits after Scenario AQ). GG2f1's rows follow GG2e2's in GW.

## Out of scope

- the read-only actions and the live Matrix (GG2e2);
- seeding and expanding (GG2f1);
- the batch job (GG2f2);
- editing (GG2g);
- the inspector (GG3d1);
- writing `PARITY_EXCEPTIONS.yaml` (the owner's);
- any Conduit change;
- `apps/workspace`;
- the Default tree.

**Stop and ask** if the proxy must change to carry the page's socket, or if a reader's frames could reach another reader.

## Proposed `slices.tsv` row (not added)

```
GG2e1	GG2	The case's live working set at /cases/graph?case=…: GG2a's module fed by the delta stream through CO3's proxy with GG2c's client, the cap frame said in words, a socket's end said truly; scripts off a sentence and the case's saved views as links; merges after WS4b; WAITS FOR THE OWNER before its merge: the parity line (GG2e1_PARITY_LINE.diff) applied (GG2e question 2 (a), the owner 26 November; the rest standing (a), D274; draft drafts_2026-11-28)	GG2b,GG2c	2	lane/slice-GG2e1	full	OspreyFlow_Core/apps/pages/test/govuk/live-graph.test.ts,OspreyFlow_Core/apps/pages/test/govuk/live-graph.spec.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/live-graph.test.ts && npm run test:govuk --workspace apps/pages -- live-graph.spec.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2e1 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm test --workspace packages/glass-shared && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && node scripts/version_isolation_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2e1 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_live_graph_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/glass_trees/test_version_isolation_check.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2e1 uv run --frozen ruff check .
```
