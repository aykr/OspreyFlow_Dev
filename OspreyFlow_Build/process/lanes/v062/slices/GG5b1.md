# Slice GG5b1 · GG5 · The map's way through the page service: ranged tiles through the forwarder, the label glyphs served by the page service, and the MapLibre 6.19 module with its same-origin worker, proved on GG5a's fixture page

- **Build id:** GG5 (the `map-and-site-plans` row, `apps/pages/FUNCTIONS.yaml:393-399`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:** GG2a (`DRAWING_MODULES` and `buildDrawingModule`, on `away/GG2a`, not merged); WS4a (I20's version-window
  check, `scripts/same_drawing_versions_check.mjs`, in the first train, not merged). GG5a and GG6 are merged. **No hold
  by decision 9:** this part draws nothing with Sigma, GG5 is R8 and not R4, and decision 9's map condition ("not
  merged until GG6", `spec/06_DECISIONS.md:41105-41106`) is met.
- **Split:** GG5b, the 26 November draft, is size L. It is two parts:
  - **GG5b1 (this part):** the tiles, glyphs, worker and module, on a fixture page, with no route.
  - **GG5b2:** the case map of a saved view's places.

  GG5c's and GG5f's rows name "GG5b". They mean GG5b2 (see `INDEX.md`).
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. **Its merge waits for the owner's approval of `GG5b1_ADR152_AMENDMENT2_NOTO.diff`** (question 4b, ruled
  in the owner's words: "an ADR-152 Amendment 2 diff adding Noto Sans for map glyphs only"). The diff is written, beside this brief, for
  him to approve and apply (O4).

## What

A MapLibre map on a page-service page draws its basemap, its labels and its worker entirely through the page
service, under the page service's one policy, with nothing from another origin. Three gaps stop it today, and this part
closes each:
1. The forwarder does not carry ranges.
2. Nothing in a GOV.UK deployment serves the glyphs.
3. No production-built map module exists.

GOV.UK only. No page and no route: the proof is GG5a's fixture page in `apps/pages/test/csp/`.

**The answers (each (a) unless ruled, and why):**

3. **(a) `Range` through the forwarder, for every path.**
   - The forwarder sends a `GET`'s `Range` header upstream.
   - It copies back `Content-Range`, `Accept-Ranges` and `Content-Length` with a `206`, as the Conduit sends them.
   - A malformed `Range` is passed as given, for the Conduit to answer.
   - Today `headersFor` (`apps/pages/server/forward.ts:345-357`) sends no `Range`, and `COPIED_BACK` (:89, used
     :383-386) copies only `Content-Type`, `Content-Disposition` and `X-Guide-Version`. GG5a's report found that with
     no `Range` no tile draws (`away/GG5a_AWAY_REPORT.md:183-185`).
   - The local-source route is `GET` only (`services/api/app.py:9561-9598`, a `FileResponse` that answers ranges
     itself, docstring :9577-9579). The tiles route is at :9488-9558.
   - Why (a): the Conduit decides which answers range, and the forwarder only stops dropping the headers.
4. **(a) The page service serves the glyphs** at `/assets/pages/glyphs/{fontstack}/{range}.pbf`, from the tiles folder's
   `fonts/`. The renderer mounts that folder read-only into `pages` in every shape, beside the workspace's own mount
   (`harness/render.py:1151-1161`, `GLYPHS_CONTAINER_PATH`).
   - The fontstack must be one the list names, and the range `\d+-\d+`. Anything else answers 404, before any file is
     opened.
   - Why (a): a GOV.UK deployment whose tree is complete runs no workspace (ADR-152 Amendment 1, decision 2), so
     nothing else would serve them. The workspace's `nginx.conf.template:131-137` is the only `/fonts/` today.
4b. **Ruled in the owner's own words** (26 November): "an ADR-152 Amendment 2 diff adding Noto Sans for map glyphs only".
   - The diff is `GG5b1_ADR152_AMENDMENT2_NOTO.diff`, item 6. When the owner has applied it, `fonts.json` gains the
     entry (role `map-glyphs`, 400, OFL-1.1, licence register row F4).
   - `test_fonts_list.py` learns to read a map style's `text-font` and `glyphs`, in the shape `style.ts` writes them
     (`apps/workspace/src/map/style.ts:106`, :164). It is shown red on a planted unlisted fontstack first.
   - **The builder never edits `spec/06`.**
5. **(a) The worker.** `maplibre-gl`'s worker is bundled as its own same-origin file, served as `.js`. The assets
   handler has no `.mjs` type (`away/GG5a_AWAY_REPORT.md:193-194`). It is named by `setWorkerUrl`, as GG5a ran it and as
   the workspace does (`apps/workspace/src/map/maplibreWorker.ts:16-20`). Why (a): `worker-src 'self'` holds
   (`apps/pages/server/headers.ts:40`).
6. **(a) `DRAWING_MODULES` gains `map: ["maplibre-gl"]`.** `ALLOWED_DRAWING`, the page bundles' list, stays empty
   (`scripts/assets.mjs:31` on main). The module is `apps/pages/modules/map/index.ts`. It exports `mountMap(container,
   style, options)` and a readiness attribute, set at MapLibre's first `idle` after the style loads.
   - `maplibre-gl` stays pinned exactly at 6.19.0, the workspace's resolved version (`apps/pages/package.json:26`,
     GG5a's), with I20 green.
   - The scoped-package rule (`assets.mjs:182`: a path's first segment) is unchanged here. GG5f's brief takes it.
7. **(a) The page service's one policy, unchanged.** GG5a's run found that MapLibre needs no `blob:` and no
   `unsafe-eval` (`away/GG5a_AWAY_REPORT.md:8-9`), and `headers.ts:36-42` stays as it is. Why (a): no change is needed,
   and any change would be the owner's first.

## What exists today (re-read at `b79164850`)

- **GG5a (merged)** left a fixture page and a spec: `apps/pages/test/csp/map.spec.ts`, `mapServer.ts`,
  `page/map-page.ts`, `page/map-page.css` and `playwright.config.ts`, run by `npm run test:csp`. Its CI wiring
  (`apps/pages/test/csp/ci-wiring.patch`) is approved but not applied.
- **The forwarder** carries every `/v1` path but three (`forward.ts:97-101`: the stream, `ws-ticket` and
  `session-events`). It refuses multipart to a route not in `UPLOAD_ROUTES` (:107-112, :433-437).
- **The pages service in the harness:** `harness/pages_service.py` (`enabled` :58, `route_paths` :86,
  `service_environment` :114) and `harness/cloud_platform/profile.yaml:27`. No tiles or glyph mount for `pages` exists.
- **The glyph files** are installed as `<tiles>/fonts/<font>/*.pbf` by `scripts/fetch_basemap_glyphs.py:70-84`, with
  `STYLE_FONTS = ("Noto Sans Regular",)` (:32).
- **`spec/02_GLASS_FRONTEND.md:2072-2101`** describes the local-source route and the glyphs as "proposed, not settled
  spec". This part writes the page service's half (the forwarder's ranges, the glyph path) into it (rule 11).

## Round 1's steps

1. Write Scenario MP's first rows in `spec/08` and the acceptance test files first. Show them red on main:
   - the forwarder drops `Range`;
   - no glyph route;
   - no map module.
2. **The forwarder's ranges** (item 3), with its tests.
3. **The glyph route** (item 4):
   - a setting in `server/config.ts` names the mounted folder;
   - the route sits under `/assets/pages/glyphs/`, a path the server owns (`server/pages.ts`'s `OWNED`);
   - the mount goes in `harness/render.py` for every shape, with `tests/harness/test_pages_setting.py` for each.
4. **The module and the worker** (items 5 and 6), built by `buildDrawingModule("map")`. The fixture page in
   `test/csp/page/` uses the module, the page service's own glyph path and the ranged basemap through the real
   forwarder.
5. **The font list.** Add `test_fonts_list.py`'s map-style cases, red first. Add `fonts.json`'s entry only once the
   owner has applied the amendment. Until then, the case for the real style is marked as waiting for it, and the
   planted cases run.
6. Write the page service's half into `spec/02` §3.4. Run the checks, the render tests and every plant.

## Acceptance test (new, red on main)

All are red on main:
- `OspreyFlow_Core/apps/pages/test/server/forward-range.test.ts` (vitest; new);
- `OspreyFlow_Core/apps/pages/test/server/glyphs.test.ts` (vitest; new);
- `OspreyFlow_Core/apps/pages/test/csp/map-module.spec.ts` (Playwright, Chromium and WebKit; new);
- `OspreyFlow_Build/tests/glass_trees/test_fonts_list.py` (extended).

**The fixture Conduit models the real route's refusals** (rule 15's second example):
- a `416` for a range past the file's end, with `Content-Range: bytes */<size>` as Starlette's `FileResponse` sends it;
- a `404` for an unknown provider;
- the "basemap not built" `404` (`app.py:9591-9596`).

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | A ranged `GET` of the PMTiles file through the forwarder | `206`, `Content-Range`, and exactly the bytes asked for | today's forwarder (red as it stands: no `Range` carried) |
| 2 | The ranged answer's headers | `Content-Length` and `Accept-Ranges` as the Conduit sent them | the forwarder's own length sent in place of the Conduit's |
| 3 | A range past the end | the Conduit's `416` and its `Content-Range`, passed through | the forwarder answering `416` itself |
| 4 | A `GET` with no `Range` | the whole answer, `200`, as today | `Range: bytes=0-` added by the forwarder |
| 5 | A glyph range of the listed font | the file's bytes, from the mount | the route reading the workspace's `/fonts/` path |
| 6 | A fontstack the list does not name, `..` in either part, a range not `\d+-\d+` | 404 before any file is opened | the path joined before the check (`../` reaches outside the folder) |
| 7 | The module on the fixture page | `idle` reached with the basemap drawn and a label layer drawn; the ready attribute set | the readiness check on an event that never fires, shown first |
| 8 | The worker | same-origin, served as `.js`; `worker-src 'self'` holds | `setWorkerUrl` given another origin (GG5a's case shape) |
| 9 | The policy (I2) | no `securitypolicyviolation`, Chromium and WebKit | a style attribute set by the module |
| 10 | Nothing from another origin (I3) | no request but the page's own | `sigmaMaplibreLayer.ts:81`'s default style address copied into the module |
| 11 | The bundles | `maplibre-gl` only in the map bundle; none in a page bundle or `glass-shared` (I13); no React (I1) | a planted `import "maplibre-gl"` in a page module |
| 12 | I20 | one `maplibre-gl` across the two workspaces | a different pin in `apps/pages/package.json` |
| 13 | The font list (item 4b) | a map style naming an unlisted fontstack is refused; so is a `glyphs` template on another origin | an unlisted fontstack in the style's real `text-font` shape |
| 14 | The mount in every shape | the renderer gives `pages` the fonts folder read-only, in each shape; nowhere writable | the mount written read-write |

## Checks

`cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck`, `no_react_check.mjs`,
`version_isolation_check.mjs`, I20's check, `test_fonts_list.py`, `tests/harness/test_pages_setting.py` and the render
tests (a harness file is touched), `test_route_pins.py`, `test_page_lists_merge.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py` and `ruff check .`. `make licence-check` runs in the merge's full gate.

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: a new **Scenario MP — A case's map on the page service (slices GG5b1 and GG5b2,
GOV.UK tree)**, **after Scenario TS** (trends shown together, `## Scenario TS` at :849) and before Scenario CS. GG5b2's
rows follow these. GG5c's heat rows follow GG5b2's.

## Out of scope

- a page or a route (GG5b2);
- the places of a view (GG5b2);
- the heat layer (GG5c);
- boundaries and gazetteers (GG5d);
- site plans (GG5e);
- the graph on the map (GG5f);
- the scoped-package allow-list rule (GG5f);
- any change to `headers.ts`;
- any Conduit change;
- editing `spec/06` or `PARITY_EXCEPTIONS.yaml`;
- `apps/workspace`.

**Stop and ask** if MapLibre needs `blob:` or `eval` on this page after all, if a shape cannot mount the fonts folder
read-only, or if a range answer would need the forwarder to read the body.

## Proposed `slices.tsv` row (not added)

```
GG5b1	GG5	The map's way through the page service: Range carried by the forwarder (206, Content-Range, Accept-Ranges and the Conduit's length copied back), the label glyphs at /assets/pages/glyphs/ from a read-only mount in every shape, and the MapLibre 6.19 module with its same-origin worker (DRAWING_MODULES map), proved on GG5a's fixture page under the unchanged policy; WAITS FOR THE OWNER before its merge: the ADR-152 Amendment 2 diff (GG5b1_ADR152_AMENDMENT2_NOTO.diff; question 4b, the owner's words of 26 November) (the rest the owner's standing (a), D274; draft drafts_2026-11-28)	GG2a,WS4a	2	lane/slice-GG5b1	full	OspreyFlow_Core/apps/pages/test/server/forward-range.test.ts,OspreyFlow_Core/apps/pages/test/server/glyphs.test.ts,OspreyFlow_Core/apps/pages/test/csp/map-module.spec.ts,OspreyFlow_Build/tests/glass_trees/test_fonts_list.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/server/forward-range.test.ts test/server/glyphs.test.ts && npm run test:csp --workspace apps/pages -- map-module.spec.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG5b1 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_fonts_list.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && node scripts/version_isolation_check.mjs && node scripts/same_drawing_versions_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG5b1 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_fonts_list.py ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/glass_trees/test_version_isolation_check.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py ../OspreyFlow_Build/tests/harness/test_render.py ../OspreyFlow_Build/tests/harness/test_map_settings_render.py ../OspreyFlow_Build/tests/harness/test_cloud_platform_render.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG5b1 uv run --frozen ruff check .
```
