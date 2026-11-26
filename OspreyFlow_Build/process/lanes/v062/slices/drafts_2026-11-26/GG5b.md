# Slice GG5b · GG5 · The map module on the page service: MapLibre 6.19 with its worker, its basemap and its glyphs reached through the page service, under the strict policy, first on a case map of a saved view's places (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **It needs GG5a's report** (the
strict-policy run: whether MapLibre needs `blob:` or reaches `eval` under the page service's own policy). If GG5a stops on
either, this draft waits for the owner's ruling on that stop.

**Where it comes from.** The plan's row "GG5: Map and site plans on MapLibre 6 (R8)", which needs GG2; `FUNCTIONS.yaml`
row `map-and-site-plans` (:378-384: heat layer, hotspot histogram, boundary filter, gazetteers, site calibration;
scenarios A1, A2, A3, B17). ADR-152 decision 9: "**MapLibre never differs.** `pages`' map module is not merged until GG6
has moved the React workspace to the same `maplibre-gl` line" (**GG6 merged**: `ae315fac9` on `origin/main`); decision 8:
`worker-src 'self'`, and `blob:` in `img-src` "on map pages only, if the browser run shows MapLibre needs it". **The map
module draws no Sigma**; the graph layer on the map is GG5f, after WS4b.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The basemap's bytes.** Tier 1's local PMTiles file is served by the Conduit at
  `GET /v1/map/local-source/{provider_id}` (`services/api/app.py:9551-9588`), a `FileResponse` that "answers a
  byte-`Range` request itself"; PMTiles' client "reads its own directory and tile blocks via byte ranges against the
  single file, never downloading it whole" (`spec/02_GLASS_FRONTEND.md` about lines 2072 to 2101, "proposed, not settled
  spec"). Tiers 3 and 4 use `GET /v1/map/tiles/{provider_id}/{z}/{x}/{y}` (:9478-9499), principal only, not audited.
  `GET /v1/map/providers` (:9341) is the public map configuration.
- **The page service's forwarder carries every `/v1` path but three** (`apps/pages/server/forward.ts:97-101`), so both
  routes reach the Conduit. **But it sends no `Range` header upstream** (the headers it builds, :345-357) **and copies
  back only `Content-Type`, `Content-Disposition` and `X-Guide-Version`** (:89, :383-386): no `Content-Range`, no
  `Accept-Ranges`. **A PMTiles basemap cannot be read through the forwarder as it stands.**
- **The glyphs.** The style names `glyphs: "/fonts/{fontstack}/{range}.pbf"` (`apps/workspace/src/map/style.ts:106`),
  served by **the workspace's nginx** from the tiles folder's `fonts/` (`spec/02` the same passage; installed by
  `python -m scripts.fetch_basemap_glyphs`). The page service serves no `/fonts/`. **A GOV.UK deployment whose tree is
  complete renders no workspace** (ADR-152 Amendment 1 decision 2), so nothing would serve the glyphs. ADR-152 Amendment 2:
  fonts are listed once in `packages/design/fonts.json`, and a test fails if either front end loads a font the list does
  not name.
- **The worker.** The workspace sets a same-origin worker (`apps/workspace/src/map/maplibreWorker.ts:10-20`,
  `setWorkerUrl`), which is what keeps `worker-src 'self'` (GG5a's draft, the bundle read).
- **An outside address in code.** `src/map/sigmaMaplibreLayer.ts:81` hard-codes `https://demotiles.maplibre.org/style.json`
  as a default style; `MapView.tsx:377` overrides it. The page module must name none (I3).
- **What a map draws.** In the workspace, the working set's located nodes are drawn by Sigma over the map
  (`MapView.tsx:343`, :382, `bindMaplibreLayer`). **No HTTP read gives a case's places outside a working set or a
  saved view** (`POST .../map/places`, :9365, is the gazetteer's place search, 2 to 100 characters, up to 25 results).
- **Site plans' upload** (`POST .../sites`, :10198, multipart) **is not carried by the forwarder** (:50-52, :433-439:
  415, "the owner's ruling is needed"). That is GG5e's question, not GG5b's.

## Acceptance (red before, green after)

Scenario **MP** (new), written first; `apps/pages/test/govuk/csp/map.spec.ts` (I2 and I3 for a map page, Chromium and
WebKit) and `apps/pages/test/govuk/map.test.ts`, red (no page, no module), green after; GG5a's standing test still green;
I20 green (one `maplibre-gl` across both workspaces).

## Questions for the owner (the proposal first)

1. **What the first map page draws.** (a) **A saved view's located places** (GG2b's `CaseViewOpened`, the nodes with a
   position), **as MapLibre's own circle layer**, read-only, with a table of the same places for scripts off (name, type,
   and the place's position in words). The graph drawn over the map is GG5f's. (b) A test page alone, with no data, and
   the case map later.
2. **The look.** (a) **Circles coloured by type from the tokens, labelled as the Matrix names them**, which is not the
   workspace's Sigma drawing; **I6 is about functions, not looks**, and the owner may prefer to wait for GG5f. (b) Wait
   for GG5f and draw nothing until then.
3. **Range through the forwarder.** (a) **The forwarder carries `Range` upstream on `GET` (the local-source route is
   `GET` only, `app.py:9551`: no `HEAD`), and copies back `Content-Range`, `Accept-Ranges` and `Content-Length` with a
   `206` as the Conduit sends it**, for every path (the Conduit decides which answer ranges), with its tests (a ranged
   `GET`, a body that ranges, and the length the Conduit sends, which the forwarder today rebuilds rather than copies,
   `forward.ts:345-357`); a malformed `Range` is passed as given and the Conduit answers it as it does. (b) Only for `/v1/map/local-source/*`. (c) The page service reads the file itself: a second reader of the tiles
   folder, not proposed.
4. **The glyphs.** (a) **The page service serves `/assets/pages/glyphs/{fontstack}/{range}.pbf` from the tiles
   folder's `fonts/`, mounted read-only into the `pages` service by the renderer** (a harness change, in every shape), and
   the module's style names that path. (b) The map draws unlabelled on the page service until a later slice.
4b. **The glyphs' font and ADR-152 Amendment 2 (the owner's).** The style's labels are "Noto Sans Regular"
   (`apps/workspace/src/map/style.ts:164`, :185), and Amendment 2's list names only Atkinson, IBM Plex Mono and GDS
   Transport (`spec/06_DECISIONS.md` about 42010 and 42016). Amendment 2's test looks for font imports, `@font-face`
   rules, font files and font addresses in source (about 42031 to 42035), which a fontstack name in a map style matches
   none of, so **the workspace already serves a font the list does not name, and no test sees it.** (a) **Stop and bring
   it: the owner rules whether map glyphs are a font under Amendment 2** (if they are, the list gains Noto Sans with its
   licence, or the style changes font, and the test learns to read a style's `glyphs` and `text-font`). (b) Your words.
5. **The worker.** (a) **`maplibre-gl-worker.mjs` bundled as its own file in the page service's assets, named by
   `setWorkerUrl` with a same-origin address**, exactly as GG5a ran it. (b) Your words.
6. **The drawing allow-list.** (a) **`DRAWING_MODULES` (GG2a's, `apps/pages/scripts/assets.mjs`) gains
   `map: ["maplibre-gl"]`; the page bundles' `ALLOWED_DRAWING` stays empty.** (b) Your words.
7. **A map page's policy.** (a) **The page service's one policy, unchanged**, unless GG5a found a need; any change to
   `server/headers.ts` is the owner's word first. (b) Your words.
8. **The cap.** A saved view over the cap is GG2b's typed refusal. (a) **The same three options in words; no map
   drawn.** (b) A sentence.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A saved view with 12 located places, scripts on | the map reaches `idle` with the basemap drawn and 12 circles; the table of 12 below | the readiness check on an event that never fires (red first) |
| 2 | The same, scripts off | the table of 12, whole | the table drawn only by the module |
| 3 | A ranged `GET` of the PMTiles through the forwarder | `206`, `Content-Range` and the bytes asked for | today's forwarder (red as it stands: no `Range` carried) |
| 4 | The ranged answer's headers | `Content-Length` and `Accept-Ranges` as the Conduit sent them | the forwarder's rebuilt length sent in place of the Conduit's |
| 5 | Glyphs | the label layer drawn; the glyph path the page service's own | the style naming `/fonts/` (the workspace's) |
| 6 | The glyph font (question 4b) | the owner's ruling carried out; if Amendment 2 covers glyphs, its test reads the style's `text-font` and is red on a planted fontstack the list does not name | a fontstack the list does not name, in the style's real `text-font` shape |
| 7 | The policy (I2) | no `securitypolicyviolation`, Chromium and WebKit | a style attribute set by the module |
| 8 | Nothing from another origin (I3) | no request but the page's own | `sigmaMaplibreLayer.ts`'s default style URL copied into the module |
| 9 | The worker | same-origin; `worker-src 'self'` holds | `setWorkerUrl` given another origin (GG5a's case 5 shape) |
| 10 | A basemap not built (the route's 404, whose detail names the server's file path, `app.py:9584-9586`) | "The map's basemap has not been built" in the page's own words, never the route's detail; the table whole | the detail shown (a server path on the page) |
| 11 | No located place | "Nothing in this view has a map position"; the basemap at its own centre | a camera fitted to an empty box (the 8 October fault) |
| 12 | Two readers of different clearance | each map and table holds only what the route sent them | a place read from a second route |
| 13 | I20 and I13 | one `maplibre-gl` in both workspaces; none in `glass-shared` | a different pin in `apps/pages` |
| 14 | Keyboard | the map's own controls and the table reachable (rule 13); `MAP_VIEW_ACTIONS` offered ones covered | a control out of the tab order |

## Files touched

`spec/08` (MP); `spec/02` (the page service's map: the glyph path, the forwarder's ranges, the local-source passage
settled); `apps/pages/modules/map/` (new), `scripts/assets.mjs` (`DRAWING_MODULES`), `package.json` (`maplibre-gl`
pinned exactly to the workspace's resolved 6.19.0); `server/forward.ts` (question 3) and its tests; `server/` (the
glyph route, question 4; the page); `tree-govuk/` (the page); `harness/` (the read-only mount of the tiles folder's
`fonts/` into `pages`, question 4) and `OspreyFlow_Build/tests/harness/test_pages_setting.py`; the tests above.

## Checks (frozen when cut)

GG2b's list adapted, with GG5a's standing test, `make licence-check`, the forwarder's tests, the font-list test of
Amendment 2, and the render tests in full (a harness file is touched).

## Out of scope

The heat layer and the hotspot histogram (GG5c); the boundary filter and gazetteers (GG5d); site plans (GG5e); the graph
on the map (GG5f, after WS4b); rotation and pitch; any Conduit change.
