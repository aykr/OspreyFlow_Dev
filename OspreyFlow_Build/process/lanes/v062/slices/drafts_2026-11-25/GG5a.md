# Slice GG5a · GG5 · The strict-policy run: MapLibre 6.19 under the page service's own content security policy, in a real browser, red first (an extension of `slices/GG5a.md` with the owner's questions and a table of cases)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. **It extends the conductor's brief of 21 November (`slices/GG5a.md`, unchanged on main),
whose "What" items 1 to 5 still stand unless a ruling below changes them.** GG5a has no row in `slices.tsv` and no run
on record. The owner's word of 21 November (file 009, answer 10, `RULINGS.md` line 419) is to brief GG5 now, run the
strict-policy run first, record that the 18 November claim of a CSP build is void, and keep rotation and pitch with
GG5. His ruling of 22 November (file 013 item 9, `RULINGS.md` line 431) adds that the map's plain files are left for
GG5a and GG5b.

**Question 0, rechecked against the plan's row (the owner, 25 November 2026, later the same day):** "**GG5: Map and
site plans on MapLibre 6 (R8)**", which **needs GG2**. **The reading holds.** **One thing to confirm, with no change
proposed:** the brief of 21 November says GG5a does not wait for GG2, on the owner's word of that day (file 009,
answer 10: "brief GG5 now, the strict-policy run on MapLibre 6.19 first"). The plan's row says GG5 needs GG2.
**Proposed: the 21 November word stands for GG5a alone.** GG5a is a test-only page, never routed, with no Sigma, so
nothing in it reaches a person. **GG5b (the map and site plans themselves) waits for GG2**, as the row says; for its
graph layer it also waits for WS4 (decision 9).

## What exists today (re-read on 25 November 2026 at `4f77858a5`; re-read again, lines move)

- **The policy.** `OspreyFlow_Core/apps/pages/server/headers.ts`: `helmet({ contentSecurityPolicy` (:33),
  `useDefaults: false` (:34). Directives :36 to :46: `default-src 'self'`; `script-src 'self'` and the nonce;
  `style-src 'self'` and the nonce; `img-src 'self' data:` (:39); `worker-src 'self'` (:40); `connect-src 'self'`
  (:41); `frame-src 'none'`; `frame-ancestors 'none'`; `object-src 'none'`; `base-uri 'self'`; `form-action 'self'`.
  It has no `unsafe-inline`, no `unsafe-eval`, no `blob:` and no map exception.
- **What decision 8 says (`OspreyFlow_Build/spec/06_DECISIONS.md` about lines 41083 to 41089).** "`img-src 'self'
  data:` (**and `blob:` on map pages only, if the browser run shows MapLibre needs it**)"; `worker-src 'self'`
  (MapLibre 6's worker served from the page's own address and named by `setWorkerUrl`); "No `unsafe-inline`, no
  `unsafe-eval`". **The brief of 21 November says "decision 8 allows no exception".** That is right for `unsafe-eval`
  and `worker-src`, but **decision 8 already allows `img-src blob:` on map pages** if the run shows it is needed
  (question 1).
- **MapLibre.** The workspace pins `"maplibre-gl": "^6.4.1"` (`OspreyFlow_Core/apps/workspace/package.json:36`), and
  the lockfile resolves 6.19.0 (`OspreyFlow_Core/package-lock.json` about line 4754). **`apps/pages/package.json` has no
  MapLibre, Sigma or graphology pin.** `apps/pages/scripts/assets.mjs` (about lines 31 to 33) refuses every drawing
  import (`ALLOWED_DRAWING = []`). The away checkout has no `node_modules`. The installed package was read in the main
  checkout on this server (`~/ospreyflow/OspreyFlow_Core/node_modules/maplibre-gl`, version 6.19.0). Its `dist` holds
  `maplibre-gl.mjs`, `maplibre-gl-worker.mjs`, `maplibre-gl-shared.mjs`, their `-dev` twins, maps, `.d.ts` and the
  CSS, and **no CSP build** (the 21 November finding stands).
- **The worker, read from the minified `maplibre-gl.mjs` (single-letter names are the bundle's own).** The function that
  starts a worker (`async function Ll`) takes `WORKER_URL` (set by `setWorkerUrl`) or the default beside the bundle. It
  then chooses:
  - if the page's origin is `"null"` (a sandboxed page), the worker script is fetched and run from a `data:` URL;
  - **if the worker address has the page's own origin, `new Worker(url, {type: "module"})` is called directly**, with
    no `blob:`;
  - if the address is **cross-origin**, a Blob of `text/javascript` holding `import "<url>"` (or the fetched script)
    becomes an object URL, which needs `worker-src blob:` under a strict policy.

  The workspace sets a same-origin worker: `OspreyFlow_Core/apps/workspace/src/map/maplibreWorker.ts:10-11` (the
  `?url` import of `maplibre-gl/dist/maplibre-gl-worker.mjs`) and :16 to :20 (`selfHostMaplibreWorker`,
  `setWorkerUrl` at :18). **So `worker-src 'self'` should hold, but only because the worker address is same-origin.**
  Case 5 plants the other branch.
- **The image path, read the same way.** An image (sprite or raster tile) is decoded with
  `typeof createImageBitmap == "function" ? <Blob → createImageBitmap> : <new Image() with src =
  URL.createObjectURL(blob)>`. The first branch makes a Blob but **no URL**, so `img-src` is not consulted. **Only the
  second branch, in a browser without `createImageBitmap`, needs `img-src blob:`.** Current Chromium and WebKit both
  have `createImageBitmap`, so the expectation is that neither needs `blob:`. Case 6 plants the fallback.
- **The `eval` branch.** `maplibre-gl-worker.mjs` has a `globalThis.eval` on a non-module branch (about line 9 of the
  minified file). It was not traced to a caller on 21 November or today.
- **The page service's browser runners.** `apps/pages/keyboard/playwright.config.ts` and
  `apps/pages/test/govuk/playwright.config.ts` exist, with the scripts `test:keyboard` and `test:govuk`
  (`apps/pages/package.json` about lines 9 to 12, `@playwright/test` about line 15). There is **no `test/csp/`
  folder**. `apps/pages/test/` holds `default/`, `fixtures/`, `govuk/`, `server/` and `support/`. `apps/pages/modules/`
  holds only `studio-frame.ts`. *The 21 November brief's "if `apps/pages` has no browser runner yet, add the smallest
  one" is out of date: two runners exist.*
- **GG6's fixture.** `apps/workspace/keyboard/map-tiles-harness.tsx` (80 lines);
  `apps/workspace/keyboard/fixtures/map-tiles.pmtiles` (*the 21 November brief put it directly under `keyboard/`*);
  `apps/workspace/map-build/playwright.config.ts` (24 lines).
- **Tiles in a deployment.** The page service has no forwarder for tiles or glyphs (nothing under `apps/pages/server`
  names them). The Conduit's tile route is `GET /v1/map/tiles/{provider_id}/{z}/{x}/{y}`
  (`OspreyFlow_Core/services/api/app.py:9408`, handler :9409, `PrincipalDep` :9415). A deployed map would reach it
  through PL10's `/v1` forwarder, and that run is owed to GG5b.
- **The map's functions** (`FUNCTIONS.yaml` row `map-and-site-plans`, slice GG5, scenarios A1, A2, A3, B17):
  - heat layer: `apps/workspace/src/map/MapView.tsx:72` and :196 to :201, MapLibre's own `heatmap` layer;
  - hotspot histogram: `HotspotHistogram.tsx:68`;
  - boundary filter: `BoundaryFilterTool.tsx:49` and `boundaryLayer.ts:38`;
  - gazetteers: `gazetteers.ts:104` and :114;
  - site calibration: `apps/workspace/src/site/SiteCalibrationWizard.tsx:77` and `siteLayer.ts:36` and :86.

  `src/map/` is 33 files and about 3,450 lines that are not blank. **Nothing uses bearing or pitch today.** The one hit
  is a comment, "disable camera rotation" (`src/map/sigmaMaplibreLayer.ts:91`), which bears on rotation and pitch
  (N22, GG5b's). In `spec/08` the scenarios are table rows, not headings: A1 (about lines 66 and 81), A2 to A5 (about
  line 82, one row), B17 (about line 63). A3 has no row of its own.

## Questions for the owner (the proposal first)

1. **If the run shows `img-src blob:` is needed.** (a) **Stop and bring it, as the 21 November brief says, even though
   decision 8 would allow it on map pages.** The reading above expects no need in either browser, so a need would be a
   surprise to explain before it is allowed. The report would give the call, the browser and the violation's text. (b)
   Allow `img-src blob:` on the map's test page at once, as decision 8 permits, and report it. **`worker-src blob:` and
   `unsafe-eval` are never allowed (decision 8): the run stops for them whatever is chosen here.**
2. **Browsers.** (a) **Chromium and WebKit**, as the brief and I2 say. (b) Add Firefox, which no other gate runs.
3. **Where the spec lives.** (a) **`apps/pages/test/csp/map.spec.ts`, with its own `playwright.config.ts` and a
   `test:csp` script.** It belongs to no tree, because the map module is kept once for both (decision 6). I2's
   per-tree specs (`test/<tree>/csp/every-page.spec.ts`) come with the first routed map page (GG5b). (b)
   `test/govuk/csp/map.spec.ts` under the existing GOV.UK runner.
4. **How MapLibre reaches the test page.** (a) **`maplibre-gl` as a devDependency of `apps/pages`, pinned exactly to the
   workspace's resolved 6.19.0** (I20: one version in both). It is bundled by the test's own esbuild call, and
   `ALLOWED_DRAWING` stays empty, since no product page draws a map yet and the test page is never a route. It passes
   `make licence-check` (BSD-3-Clause, on `spec/00` §7's allowlist). (b) Load the workspace's installed copy by path,
   with no dependency in `apps/pages`. That avoids a pin but leaves a test reaching into another workspace's
   `node_modules`.
5. **The tile fixture.** (a) **The test server reads GG6's `apps/workspace/keyboard/fixtures/map-tiles.pmtiles` by path**
   (a file read, not an import, so I5's import boundary is untouched), and the report names it. (b) A copy under
   `apps/pages/test/fixtures/`, with a test that the two copies' SHA-256 values are equal.
6. **The `eval` branch.** (a) **The builder traces it.** If no style, tile or option the product could send reaches it,
   the report says "not reached", with the evidence (the calls on the way), and plants nothing. If something reaches
   it, that is a stop, because `unsafe-eval` is never allowed. (b) Plant a non-module worker so the branch runs, and
   show the policy refuses it. This proves only that the browser enforces the policy, not that the product avoids the
   branch.
7. **What the standing test guards.** (a) **The run stays in the pages' gate as a standing test**, so a MapLibre update
   that takes a new path (a blob, an eval or an outside request) turns it red before a release. It joins `make ci` only
   as an owner's diff to the Makefile, after it has been shown red (rule 15). (b) A one-off run whose report is the
   result. Not proposed: the next MapLibre update would go unchecked.

## The table of cases (each red first; planted faults at the real call site: rule 15)

The page is test-only. The real header builder of `headers.ts` sends its policy, the worker is set as
`maplibreWorker.ts` sets it, and the style, tiles, glyphs and sprite are synthetic and served from the test's own
origin. Each case runs in Chromium and WebKit and records (a) every `securitypolicyviolation` event, (b) every request
whose origin is not the test's own, and (c) the map reaching `load` and `idle` with at least one tile drawn.

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | The map under the real policy | (a) none, (b) none, (c) true, in both browsers | the readiness check pointed at an event that never fires (red: never ready), shown before any green is believed |
| 2 | The policy actually sent | the response's `Content-Security-Policy` is the header builder's own output for that request (nonce aside), not a copy of its text | a test page that sends its own weaker policy (`img-src *`): red, naming the header |
| 3 | `worker-src 'self'` removed from the policy as the builder makes it | red with a named `worker-src` violation | the planted policy itself |
| 4 | A style that asks for a tile, a glyph range or a sprite from another origin | red, naming each request (b) and its violation (`connect-src` or `img-src`) | one style per resource kind, each the shape a real style file takes (`tiles: ["https://…"]`, `glyphs`, `sprite`) |
| 5 | The worker set to a cross-origin address (`setWorkerUrl("https://other.test/…")`) | red with a `worker-src` violation for a `blob:` worker: shows that the same-origin worker is what keeps `worker-src 'self'` | `setWorkerUrl` called as `maplibreWorker.ts` calls it, with the other address |
| 6 | `createImageBitmap` removed from the page before the map loads | red with an `img-src` violation for `blob:`: the only path that needs `blob:` | `delete window.createImageBitmap` in the test page, then the synthetic sprite loaded |
| 7 | A raster tile and the sprite decoded in the normal way | no violation (the `createImageBitmap` branch) | none: the green of case 1 with a raster source in the style, after case 6 is red |
| 8 | The `eval` branch | traced (question 6); "not reached" with evidence, or a stop | per question 6 |
| 9 | The report | a table, directive by directive, of what the map needed in each browser, with the violation text for each that failed, the time of the run and the browser versions | none: the verifier checks it against the run's own log |

## Checks (frozen when cut)

The new spec through its own script (a seat, with a Playwright slot; it starts only when the PL4 chain's seat is not
waiting and no merge is in its gate, as the 21 November brief says); `npm test --workspace apps/pages` (the server
tests); `npm run typecheck` and `npm run lint` for `apps/pages`; `node scripts/no_react_check.mjs`;
`node scripts/version_isolation_check.mjs` (I13: nothing in `glass-shared` imports MapLibre); `make licence-check`
(the devDependency, if question 4 is (a)); `tests/test_doc_citations_check.py`; `ruff check .` only if Python is
touched (none expected); the cheap checks of 20 November. **The builder never takes the stack lease.**

## Out of scope

The map and site plans themselves (GG5b); rotation and pitch (N22, GG5b's own); any change to `headers.ts` unless the
owner rules on a stop; the tile and glyph forwarder; I2's every-page specs; any file under `apps/workspace`; Sigma (the
map's graph layer waits for the Sigma 4 proof and WS4: decision 9); any real tile, style or font from the internet.
