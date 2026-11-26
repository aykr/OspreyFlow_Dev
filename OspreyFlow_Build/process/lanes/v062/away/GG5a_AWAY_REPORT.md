# GG5a away report: the strict-policy run, MapLibre 6.19 under the page service's own policy (26 November 2026, D246 away round)

Branch `away/GG5a`, from `origin/main` at `300e3fe96`. Nothing pushed or merged; `main` untouched. Every test ran through
`~/osprey-d246/d246_ns.sh` from `OspreyFlow_Core`, at `nice -n 19`. Synthetic data only. Not edited: `OspreyFlow_Core/Makefile`,
`OspreyFlow_Build/Makefile`, `.github/workflows/ci.yml` (its change is a patch file), `spec/06_DECISIONS.md`,
`spec/ADR_RESERVATIONS.md`, `osprey.yaml`, `data/`, `apps/pages/server/headers.ts`, anything under `apps/workspace`.

**State: done. No stop.** Under the page service's real policy, in Chromium 156 and WebKit 27.2, MapLibre 6.19 draws with no
violation and asks nothing of another origin. **It needs no `blob:` and no `unsafe-eval`, and no change to `headers.ts`.** Every
planted fault is red through the same checker that finds the real page clean. The spec is a standing test (`npm run test:csp
--workspace apps/pages`). Its CI job is a patch for the owner, and the run's facts are a diff to ADR-152 decision 8 for the
owner (`GG5a_ADR152_DECISION8_RUN.diff`, beside this report). Four questions for the owner are at the end. **Question 1 (the
`pmtiles` pin, outside ruling 4's words) is the one the merge waits on.** An independent read-only review found real gaps, and
they are fixed (see "After the review").

Read first: the brief (`slices/GG5a.md` on `origin/main`), the draft (`drafts/2026-11-25`, `GG5a.md`), the corrections
(`drafts/2026-11-26`, `INDEX.md`). The owner's rulings applied: every draft proposal (a) (D274); release scope A-full (D273).

## The rulings, as built

| Draft question | Ruling (a) | As built |
| --- | --- | --- |
| 1 `img-src blob:` if needed | stop and bring it | **Not needed** in either browser. Only a browser with no `createImageBitmap` takes the `blob:` path, shown by a plant (case 11). Nothing stopped. |
| 2 browsers | Chromium and WebKit | Both. Firefox not run. |
| 3 where | `apps/pages/test/csp/map.spec.ts`, its own config, `test:csp` | As proposed: `test/csp/playwright.config.ts` with a `chromium` and a `webkit` project. |
| 4 how MapLibre reaches the page | devDependency of `apps/pages`, exactly 6.19.0, the test's own esbuild call, `ALLOWED_DRAWING` empty | As proposed. **Also `pmtiles` 4.5.0** (the workspace's resolved version, exact) so the page reads GG6's archive through the real `pmtiles://` protocol. That second pin is my extension of (a), and question 1 below asks the owner to confirm it. |
| 5 the tiles | GG6's archive read by path | `apps/workspace/keyboard/fixtures/map-tiles.pmtiles`, read with `readFileSync` (`mapServer.ts`, `ARCHIVE_FILE`). It is never imported. |
| 6 the `eval` branch | the builder traces it | Traced: **not reached** (evidence below). Nothing planted. |
| 7 the standing test | stays in the pages' gate, joins CI only by the owner's diff | `test:csp`, and `test/csp/ci-wiring.patch` (a `pages-csp` job). `git apply --check` is clean against this branch's `ci.yml`. |

## Commits, in order

| Commit | What |
| --- | --- |
| `007a5d6dc` | `maplibre-gl` 6.19.0 and `pmtiles` 4.5.0 as exact devDependencies of `apps/pages`. The lockfile gains only those two lines: npm's own rewrite (a re-sorted key and unrelated `"peer": true` lines) was undone, and `npm ci` accepts the result. |
| `7f470e8cd` | The page, its server and the first case. Red first: on `origin/main` there is no such test. |
| `03367ebf2` | The planted faults and the directive table, work in progress. |
| `1bcaae320` | Green in both browsers, every plant red: 50 cases. |
| `0da010da2` | Typed for the pages' own `tsconfig`, the CI patch, citations written out in full. |
| `b22d61f15`, `1875a5ef7` | This report, then the two stability runs in it. |
| after the review | The worker's own policy checked, plants shown to land, the third-origin and page-alone cases, `script-src` with the nonce alone; the ADR diff; this report corrected. |

## What was built, and what is real

- **`apps/pages/test/csp/mapServer.ts`**: the test-only server. It is never a product route and never in the page registry.
  - **The real policy:** `securityHeaders()` from `server/headers.ts`, mounted first with `app.use`, as `server/app.ts:223` mounts it. Every response carries the builder's own policy: the page, the assets, the worker, the style and the tiles.
  - **The real asset route:** `assetsHandler()` at `ASSETS_PREFIX`, after the headers, as `server/app.ts:227` mounts it. The page's module and stylesheet, and MapLibre's own `dist/maplibre-gl-worker.mjs` byte for byte, are served under content-hashed names.
  - **Synthetic, made here:** the style, a raster tile, a sprite (single-colour PNGs) and a glyph range (a valid protobuf with no glyphs). Every colour is a design token, read from `packages/design/tokens.css` by name.
  - **Another origin:** a second server on another port, recording every request that reaches it.
  - **Planted policies:** each is applied to the builder's own output on its way out, on every response while that page is open (see finding 2).
- **`apps/pages/test/csp/page/map-page.ts`**: the page's module.
  - It calls `setWorkerUrl` once before any map is made, on the page's own origin, as `apps/workspace/src/map/maplibreWorker.ts:16-20` does.
  - It registers `pmtiles://` and makes one map with the product's own option (`attributionControl: false`, `MapView.tsx:377`).
  - The worker's and the style's addresses come from `<meta>` tags, so a plant changes the page's data, never its code.
  - It is bundled with the options `apps/pages/scripts/assets.mjs` gives a module: ESM, ES2018, browser, minified, no splitting.
  - It is excluded from the pages' Node `tsconfig.json` (which has no DOM library) and has its own `page/tsconfig.json`.
- **`apps/pages/test/csp/map.spec.ts`**: the spec. For each page it records:
  - **(a)** every `securitypolicyviolation` event, in the document and in each worker, plus every CSP refusal on the console of the document and of each worker (two witnesses);
  - **(b)** every request to an origin not the page's own, seen by the browser (request events, and a route that aborts anything bound for a third origin), and independently every request the other origin's own server received;
  - **(c)** `load` and `idle`, a tile block read from the archive by range, and the canvas showing the water and the land cover from the archive's tiles and the raster tile under them. Each is counted by its exact token colour in a screenshot, decoded in Node.

  `failures()` turns a record into words. The real page must have none, and each plant must be named by the same function.
- **Reused from GG6, and how:** the archive file, by path. GG6's ranged-answer rules (206 with `Content-Range`, 416 past the end) and its screenshot method are written again here, not imported (I5). **Not reused:** `map-tiles-harness.tsx` and `map-build/playwright.config.ts`. They are React and Vite, and `apps/pages` takes no React (I1). GG6's spec answers its archive by Playwright's request interception, which cannot show a policy's refusal, so this spec serves everything from a real server.

## The directive table (measured; the run's own log has a `RECORD` line per case)

How each line was found: every directive the builder sends, set to `'none'` in turn, in both browsers. Separately, the real
policy with every map path taken (the worker, the style, the archive by range, a raster tile, the sprite's two files, a glyph
range). The same in both browsers.

| Directive (as the builder sends it) | Does the map need it? | Violation text when taken away (Chromium / WebKit) |
| --- | --- | --- |
| `script-src 'self' 'nonce-…'` | **yes**: the page's own module. It needs the nonce **or** `'self'`: with the nonce alone (no `'self'`) the map loads in both browsers, because the script tag carries the nonce. `'self'` matters only to a script without the nonce. | `Loading the script 'http://127.0.0.1:PORT/assets/pages/map-page-LW46NTDY.js' violates the following Content Security Policy directive: "script-src 'none'". Note that 'script-src-elem' was not explicitly set, so 'script-src' is used as a fallback.` / `Refused to load http://127.0.0.1:PORT/assets/pages/map-page-LW46NTDY.js because it does not appear in the script-src directive of the Content Security Policy.` |
| `worker-src 'self'` | **yes**: MapLibre's worker, same-origin, `new Worker(url, {type: "module"})` | `Creating a worker from 'http://127.0.0.1:PORT/assets/pages/maplibre-gl-worker-C8564C4A.js' violates the following Content Security Policy directive: "worker-src 'none'". The action has been blocked.` / `Refused to load http://127.0.0.1:PORT/assets/pages/maplibre-gl-worker-C8564C4A.js because it does not appear in the worker-src directive of the Content Security Policy.` The map never loads. |
| `connect-src 'self'` | **yes**: the style, the archive's ranges, the raster tiles, the sprite's JSON and PNG, the glyph ranges (all `fetch`) | `Connecting to 'http://127.0.0.1:PORT/fixture/style.json?page=…' violates the following Content Security Policy directive: "connect-src 'none'". The action has been blocked.` / `Refused to connect to http://127.0.0.1:PORT/fixture/style.json?page=… because it does not appear in the connect-src directive of the Content Security Policy.` The map never loads. |
| `style-src 'self' 'nonce-…'` | **yes, for the stylesheet only** (`<link>`, `'self'`). MapLibre sets no style attribute and adds no `<style>`. With the stylesheet refused, the map still draws. | `Loading the stylesheet 'http://127.0.0.1:PORT/assets/pages/map-page-W575YNBX.css' violates the following Content Security Policy directive: "style-src 'none'". …` / `Refused to load http://127.0.0.1:PORT/assets/pages/map-page-W575YNBX.css because it does not appear in the style-src directive of the Content Security Policy.` |
| `img-src 'self' data:` | **no, for this page**: not `'self'`, not `data:`, not `blob:`. With MapLibre's defaults, sprites and raster tiles are fetched (`connect-src`) and decoded by `createImageBitmap`, which `img-src` does not govern. The product map has no controls, so MapLibre's stylesheet `data:` icons never load. **Not covered:** with the map option `refreshExpiredTiles: false`, MapLibre loads raster tiles as `<img src=url>` (`maplibre-gl-dev.mjs:14527-14529`, :14567-14590), which `img-src 'self'` governs and allows. An `image` source (the site plans' likely path, GG5b) is not in this style either. GG5b's own run must take both. | none (`img-src 'none'`: no violation, map drawn in full) |
| `default-src 'self'` | no (every fetch kind the map uses has its own directive) | none |
| `frame-src`, `frame-ancestors`, `object-src`, `base-uri`, `form-action` | no | none |
| `blob:` (any directive) | **no**, in either browser | Only with `createImageBitmap` taken away (case 11): `Loading the image 'blob:http://127.0.0.1:PORT/<uuid>' violates the following Content Security Policy directive: "img-src 'self' data:". The action has been blocked.` / `Refused to load blob:http://127.0.0.1:PORT/<uuid> because it does not appear in the img-src directive of the Content Security Policy.` |
| `unsafe-eval` | **no**: not reached (traced below) | not planted (ruling 6 (a)) |

Browsers: Chromium 156.0.8078.4 and WebKit 27.2 (Playwright 1.64.1's builds), headless, 1000 × 700, device scale 1. Main run
15:10:54 to 15:15:39 UTC (50 passed, 4.7 min), and two further full runs 15:29 to 15:39 UTC (50 of 50 each), all of the 25-case version; after the review, 15:44:58 to 15:49:22 UTC, 56 of 56.

## The table of cases (each runs in both browsers: 28 cases × 2 = 56)

| # | Case | Expected, and seen in both browsers |
| --- | --- | --- |
| 1 | The real policy, the full style | No failures. Version `6.19.0`. Worker(s) from the page's own origin (Chromium 1, WebKit 3). Every path taken (worker, style, raster, sprite JSON and PNG, glyph range, 9 tile blocks by range). Water 91,357 px, land cover 99,208 px, raster 286,283 px in both browsers, identical. |
| 2 | **Readiness plant:** the archive answered whole, ignoring `Range` (what a forwarder without `Range` returns) | `load` and `idle` reached, **no tile drawn**: `no tile block was read`, no water, no land cover, and pmtiles' own `Server returned no content-length header or content-length exceeding request. Check that your storage backend supports HTTP Byte Serving.` This shows the check is more than `load`/`idle`. |
| 3 | **Policy plant:** the page sends `img-src *` | Only `the policy sent is not the builder's own: …img-src *`. Nothing in the map notices, so only the comparison with the builder's output can. |
| 4 | `worker-src` taken out (**the brief's plant (i)**) | **Cannot go red**: only the policy-differs line. CSP Level 3 falls back from `worker-src` to `script-src`, and `script-src 'self'` allows a same-origin worker. Kept so the fallback is on record. |
| 5 | `worker-src 'none'` (the plant that does what (i) meant) | `policy violation: worker-src refused …/maplibre-gl-worker-C8564C4A.js in the document`; the map never loads. |
| 6 | The worker named on another origin (`setWorkerUrl` as `maplibreWorker.ts` calls it) | MapLibre wraps it in a `blob:` (`import "<url>"`). `worker-src refused blob`. The other origin never received the script. **The same-origin worker is what keeps `blob:` out of the policy.** |
| 7 | A style asking another origin for a vector tile | `connect-src refused <other>/tiles/{z}/{x}/{y}.pbf in the worker` (a vector tile is fetched in the worker). Nothing reached the other origin. |
| 8 | … for a glyph range | `connect-src refused <other>/fixture/glyphs/Synthetic%20Sans/0-255.pbf in the document` |
| 9 | … for the sprite | `connect-src refused <other>/fixture/sprite.json` and `…/sprite.png`, in the document |
| 10 | … for a raster tile | `connect-src refused <other>/fixture/raster/{z}/{x}/{y}.png in the document` |
| 10w | **(b) alone:** `connect-src` widened to the other origin on every response, with case 7's style | **No violation**, and the other origin's server received 4 tile requests: `request to another origin: <other>/tiles/…`. This is the case the standing test exists for: a policy that says yes to an outside request. |
| 11 | A browser without `createImageBitmap` (taken away before the page runs) | `img-src refused blob`: the only path that needs `blob:`, and the only directive refused. |
| 12 | The page adds a `<style>` while it loads | Counted: `style-src-elem refused inline`, and the console line. This proves the screenshot's one exception (finding 4) is that narrow: in WebKit this console text is word for word the one let past during the screenshot, and here it is counted. |
| 10t | **(b)'s browser half alone:** `connect-src` widened to a third origin no server answers, with a style asking it for a vector tile | No violation, nothing reached the other origin's server, and the browser's own record names `request to another origin: http://third-origin.test/tiles/…`. **Both browsers report the worker's fetches** to the request record and the route (the route aborts them, so nothing leaves the machine). The widened case 10w now also asserts the browser's record. |
| 10p | `connect-src` widened **on the page's own response alone**, with case 7's style | The worker's response still carries the builder's own policy, and the worker refuses the tile (`connect-src refused <other>/tiles/… in the worker`). Finding 2, kept as a case. |
| 13 | The table lists every directive the builder sends | the 11 names, exactly |
| 14 to 24 | Each directive set to `'none'` | the table above. Each case first asserts that the plant reached the browser (the page's policy and the worker's both carry `<directive> 'none'`). A needed directive is then refused by name and is the only one refused; an unneeded one changes nothing. With `style-src 'none'`, the map is also shown still drawing every layer. |
| 25 | `script-src` with the nonce alone | loads in both browsers (the measurement in the table's first row) |

Every case also checks **the worker's own policy**: each response that served the worker file must carry the builder's own
policy (`the worker's script was served with no policy` / `the worker's policy is not the builder's own`). Case 1 shows it
green. Cases 3 and 4 and the table show it naming the planted worker policy, and 10p shows the page-only plant leaving it alone.
The "served with no policy" branch is not shown red: no route here serves the worker without the builder's middleware.

## The traces (read in `node_modules/maplibre-gl/dist`, 6.19.0; the `-dev` twins for names, then confirmed in the minified files the browser loads)

- **The worker.** `maplibre-gl.mjs` line 5, `async function Ll` (dev `workerFactory`, `maplibre-gl-dev.mjs:14124`), in this order:
  - `WORKER_URL` or the default beside the bundle;
  - if the page's origin is `"null"`, a `data:` worker;
  - if the address is not cross-origin, `jl(e,t)`, which is `new Worker(url, {type: "module"})` (dev `createWorker`, :14093);
  - if it is cross-origin, `Il(e)`, a Blob of ``import "<url>"`` made into an object URL (dev `importAsBlobUrl`, :14119).

  Run: Chromium and WebKit both take the direct path for a same-origin address (case 1), and the `blob:` path for another origin (case 6).
- **The image fallback.** `maplibre-gl.mjs` line 5: `new Blob([...],{type:"image/png"}); r.src = URL.createObjectURL(i)` (dev `arrayBufferToImage`, :2555-2567). It is reached only from `arrayBufferToCanvasImageSource` (dev :14513) when `typeof createImageBitmap !== "function"`. Both browsers have `createImageBitmap`. Run: not taken under the real policy, taken in case 11.
- **The `eval` branch.** `maplibre-gl-worker.mjs` line 9, `globalThis.eval(code)`, in the worker's `loadScript` (dev `maplibre-gl-worker-dev.mjs:35858-35882`). It runs only for a script address that does not end `.mjs` and whose text has no top-level `import` or `export`. Its only callers:
  - the worker's `_importScript` (:35990), from the `IS` message, which only `importScriptInWorkers()` sends (`maplibre-gl-dev.mjs:64804`, via `importScript` :14378);
  - the RTL plugin's `syncState` (:23904), which only the deprecated `setRTLTextPlugin()` reaches (:64680; 6.19 has a built-in RTL implementation).

  **No style property, tile or source option reaches either. Nothing under `apps/` or `packages/` calls `setRTLTextPlugin`, `importScriptInWorkers` or `addSourceType`** (searched 26 November). So: **not reached**, and nothing was planted (ruling 6 (a)). If a later slice calls either function with a classic script, case 1 goes red on `script-src` in the worker, and that is a stop.

## After the review

An independent, read-only review (the `lane-reviewer` agent, given the brief and the files, not my conclusions) found 4
defects to fix and 1 owner question. All are dealt with:

1. The report's stability rows were placeholders when it was read: filled since (`1875a5ef7`).
2. The "changes nothing" directive cases would have passed if the plant never reached the browser: each now asserts the
   page's and the worker's policies carry `<directive> 'none'`.
3. The browser's own record of outside requests was never shown red apart from the other origin's server: case 10t (a third
   origin no server answers) and an assertion in 10w.
4. The worker's own policy was load-bearing (finding 2) but unchecked: now recorded and checked in `failures()`, with case 10p.
5. The `pmtiles` pin is outside ruling 4's words: question 1 now says the merge waits on it.

The minor points:
- **The screenshot exception's scope.** The phase is now reset after the screenshots, so the exception no longer covers anything later.
- **Case 12's dead regex alternative** is replaced by exact assertions. The WebKit console text is now asserted in WebKit only, because Chromium's text differs.
- **Overclaims.** The image path and "every path" are corrected (the `img-src` row above), and so is the page's comment on its options.
- **Case 2's assertion that is true by construction** is now marked as such.
- **`script-src 'self'`** is measured (case 25).
- **The rule-11 point** is the ADR diff.
- **The folders read** are listed below.

Not changed:
- **The worker listener's race** (installed after the worker starts). The console witness of the document and of each worker covers it, and three full runs saw no flake.
- **The patch's location**, kept beside the spec as the GOV.UK and keyboard runners' patches are kept. Item 10's point about the Makefile is question 2.

**WebKit on this account.** `webkit-2370` was installed by this session and no other lane had WebKit before it. The
libraries are linked into that build's own folder. Any later WebKit run on this account uses them, and must also set
`PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1`. The conductor should know.

**The seat.** The brief makes this a seat run with a Playwright slot. This away round had no slot: the runs were this
session's own, in its own D246 namespace with its own loopback, and took no stack lease. The conductor's seat run, when it
comes, is the run of record.

## The folders the spec reads

- `apps/pages/server/`: `headers.ts`, `assets.ts`, called, not copied;
- `apps/pages/test/csp/`: its own files;
- `apps/workspace/keyboard/fixtures/map-tiles.pmtiles`: read by path, never imported;
- `packages/design/tokens.css`: colours by name;
- `node_modules/maplibre-gl/dist/` (the worker file and, through esbuild, the module and stylesheet) and `node_modules/pmtiles/`.

## Findings

1. **The brief's plant (i) cannot turn the run red** (case 4). Taking `worker-src` out leaves the worker allowed by `script-src
   'self'` (CSP Level 3's fallback, in both browsers). The plant that shows the worker refused is `worker-src 'none'` (case 5).
   This is rule 15's second paragraph in practice: a plant must fail for the reason it claims.
2. **A dedicated worker obeys the policy on its own script's response, not its page's.** Measured: with `connect-src` widened on
   the page's response alone, both browsers still refused the worker's outside tile, under the worker's own (unwidened) policy.
   For GG5b this means a vector tile from the forwarder is checked against the policy the page service sent with the worker
   file. That is the same builder today, because `assetsHandler` sits behind `securityHeaders()`. But **a route that served the
   worker without the policy would leave the worker with none.** A test of a deployed map should read the worker response's own
   `Content-Security-Policy`.
3. **Through a forwarder that carries no `Range`, the PMTiles basemap draws nothing** (case 2). The map still reaches `load` and
   `idle`. The only signs are pmtiles' byte-serving error and an empty picture. This is GG5b's question 3 measured: the
   forwarder's missing `Range` blocks the basemap, and a readiness check of `load`/`idle` alone would pass it.
4. **Playwright's WebKit screenshot adds a `<style>` element to the page** (even with `caret: "initial"`), and the page's policy
   refuses it, on the console only and with no event. It is the test's own, not the map's. The spec lets exactly that text past,
   only while a screenshot is taken. Case 12 shows the same text counted in any other phase.
5. **Headless WebKit can present a frame short of tiles after `idle`.** The same partial picture held for 6 s, with every tile
   read. One `triggerRepaint()` before each screenshot gives the full picture, pixel for pixel the same as Chromium's. This is a
   presentation quirk of the headless browser, not a policy matter. Case 2 still shows the drawn check red when tiles really are
   missing.
6. **The assets handler has no type for `.mjs`** (`server/assets.ts`, `TYPES`). The worker must be served as `.js`, as GG6 found
   for nginx. This is for GG5b's worker route.
7. **Two reds that are on `origin/main` too** (measured in a detached worktree of `300e3fe96`, removed afterwards):
   - `npm test --workspace apps/pages`: 2 failed of 1,038, both traversal probes against deliberately naive routes (`test/server/assetsTraversal.test.ts:102`, `test/server/foundation.test.ts:203`). Identical on main in this namespace.
   - `tsc -p apps/pages/tsconfig.json`: 190 errors on main (`modules/studio-frame.ts`, `server/views/helpWords.ts` and others), and 190 here, none in `test/csp`.

   CI's own form (`npm run typecheck`, the root `tsconfig`) is clean on both. Not mine and not fixed (out of scope); named for the conductor.

## Tests run (all through D246, `nice -n 19`)

| When (UTC) | What | Result |
| --- | --- | --- |
| 14:53 | first case, both browsers | 2 passed |
| 14:58 to 15:02 | measurement pass (every plant, printed) | the table above |
| 15:10:54 to 15:15:39 | `npm run test:csp --workspace apps/pages`, the full spec | **50 passed** (4.7 min) |
| 15:27 | the checks | see below |
| 15:44:58 to 15:49:22 | the full spec after the review's fixes | **56 passed** (28 cases × 2 browsers, 4.4 min). The two stability runs above were of the 25-case version. |
| 15:52:23 to 15:57:47 | the full spec at `c8e21c3d4` (comments changed only), and the checks again: as at `0da010da2` (the same 2 vitest and 190 `tsc` reds as main, every other check passing) | **56 passed** (5.4 min) |
| 15:29:35 to 15:34:11 | full spec, stability run 2 | **50 passed** (4.6 min) |
| 15:34:11 to 15:38:43 | full spec, stability run 3 | **50 passed** (4.5 min) |

The checks, at `0da010da2`:
- **Pass:** `tsc -p apps/pages/test/csp/page/tsconfig.json`; `npm run typecheck` (root); `eslint apps/pages`; `node scripts/no_react_check.mjs`; `node scripts/version_isolation_check.mjs`; `tools.licence_check` (94 packages, all allowed) and `tools/licence_check.mjs`; `tools.doc_citations_check`; `tests/test_doc_citations_check.py` (10 passed); `tools.test_file_coverage_check`; `tools.client_name_check`; `tools.colour_drift_check`; `tools.design_check`.
- **Red, exactly as on main (finding 7):** `npm test --workspace apps/pages` (2 failed, 1,036 passed); `tsc -p apps/pages/tsconfig.json` (190).
- Not run: `ruff check .`, since no Python was touched.

**The environment for WebKit.** This machine had Chromium only, and WebKit's own libraries were missing. With no root, I fetched
the 31 Ubuntu 24.04 packages WebKit links against:
- **How:** apt's own URIs and SHA-512 hashes (`apt-get download --print-uris`, from its signed index), fetched over HTTPS from `mirrors.edge.kernel.org`, each hash checked, unpacked with `dpkg-deb -x` (no maintainer scripts);
- **Where:** `~/.local/webkit-deps`, linked into the account's own WebKit build (`~/.cache/ms-playwright/webkit-2370/minibrowser-wpe/sys/lib`);
- **Flag:** the runs set `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1`, since Playwright's host check reads `dpkg`;
- **Changed:** no system file, and no repository file.

CI needs none of this: the patch installs `--with-deps chromium webkit`. This machine's Chromium is unchanged.

## What only a deployed run would show (owed to a later slice, GG5b or its deployed check)

- tiles, glyphs and sprite through the page service's `/v1` forwarder (PL10: it carries `/v1` paths but no `Range`, finding 3) to the Conduit's tile route (`services/api/app.py:9478`, per the 26 November corrections);
- the worker file served by the deployed page service and the policy on that response (finding 2);
- the `wss` stream (CO3's proxy) under `connect-src 'self'`: a same-origin `wss:` is allowed by `'self'` in CSP Level 3 browsers. Not measured here;
- single sign-on: the page behind the session, with the identity provider's own redirects;
- whatever the front proxy adds or overrides in the headers.

**Not in this slice:** rotation and pitch (GG5b's own decision, N22). **If GG5b draws graph layers through Sigma, it waits for the
Sigma 4 proof** (decision 9; the workspace still pins `"sigma": "^3.0.0"`, `apps/workspace/package.json:41`).

## Questions for the owner (proposal first; none blocks the merge)

1. **The second pin (the merge waits on this).** Ruling 4 (a) names `maplibre-gl`. I also pinned `pmtiles` 4.5.0 (the workspace's resolved version,
   BSD-3-Clause), so the test page reads GG6's archive by the real `pmtiles://` protocol, as the product does. (a) **Keep it**
   (proposed). (b) Drop it and serve the tiles by `z/x/y` from the test server, which would no longer test the protocol path
   GG5b will use.
2. **The CI job.** `apps/pages/test/csp/ci-wiring.patch` adds a `pages-csp` job (Chromium and WebKit, `--with-deps`), anchored
   where the two pending pages patches anchor, so all three apply independently. (a) **Apply it** (proposed). Proposed only, not
   done: a line in `OspreyFlow_Build/Makefile`'s `ci`. That target runs no other Playwright suite, and ruling 7 (a) makes any
   Makefile change the owner's diff. A third diff for the owner: `GG5a_ADR152_DECISION8_RUN.diff` (beside this report) records
   the run's facts in ADR-152 decision 8, as rule 11 asks. `git apply --check` is clean.
3. **A browser with no `createImageBitmap`** would need `img-src blob:` on map pages (case 11; decision 8 allows `blob:` there
   "if the browser run shows MapLibre needs it"). Neither supported browser needs it, so nothing changed. (a) **Leave the
   policy as it is** (proposed), and say in GG5b's page that such a browser shows no sprites or raster tiles. (b) Allow `blob:`
   on map pages for such browsers. That is a change to `headers.ts`, which is the owner's.
4. **Firefox** (draft question 2 (b)) was not run, by the ruling. The spec takes a third project in one line, but this machine
   has no Firefox build. For the owner, if ever wanted.
