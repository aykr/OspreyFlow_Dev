<!-- GG6: insert everything below this comment into OspreyFlow_Build/spec/06_DECISIONS.md after line 570
     (the end of ADR-014 Amendment 1), keeping one blank line before it. Rewrite its "Not checked" paragraph
     to what GG6 proved in a browser before merging. -->

### Amendment 2 — the revisit trigger is met: `maplibre-gl` 6.x on Sigma 3, through the binding already in the tree

**Status.** Accepted by the owner, 18 November 2026 (build id GG6). It replaces Amendment 1's accepted
risk once GG6 has merged.

**Trigger (a) is met, in its own words.** `@sigma/layer-maplibre` 4.0.1 (npm, 9 November 2026) declares
`maplibre-gl: "^4.5.0 || ^5.0.0 || ^6.0.0"` (sigma.js `CHANGELOG.md`, 4.0.5: "Adds MapLibre 5 and 6 to
the `maplibre-gl` peer range"). It also declares `sigma: "^4.0.0"`. Trigger (b) is not met: 4.7.1 is
still the last `4.x`. `maplibre-gl` 5.24.1 (11 November 2026) carries the fix (its release notes list
#8189), but the advisory GHSA-jrc7-96c5-q579 still gives the affected range as `<= 6.4.0`, so
`make trivy` still fails on 5.24.1 (shown on a scratch lockfile, trivy 0.76.1, database of
18 November 2026).

**Three statements in Amendment 1 are no longer true.**
- "the binding this ADR requires": since ADR-086 Amendment 1 (29 October 2026) the product draws the
  graph over the map with its own copy of the 3.0.0 binding, `apps/workspace/src/map/sigmaMaplibreLayer.ts`.
  No file imports `@sigma/layer-maplibre`. Its only remaining effect is its peer range in
  `apps/workspace/package.json`, which is what holds `maplibre-gl` at `^4.5.0`: npm refuses
  `maplibre-gl@6.19.0` beside it (`ERESOLVE`, "peer maplibre-gl@^4.5.0 from @sigma/layer-maplibre@3.0.0").
  `@sigma/edge-curve` is in the same state: listed, imported by no file.
- "fixed upstream only in 6.4.1": see 5.24.1 above.
- "a critical XSS sanitizer bypass in `DOM.sanitize()`" in 4.7.1: `DOM.sanitize()` does not exist in
  4.7.1. It was added in maplibre-gl-js #5057 (18 November 2024) and first released in 5.0.0. In 4.7.1
  the attribution control writes the joined attribution strings into `innerHTML` with no sanitising at
  all (`src/ui/control/attribution_control.ts:176` in the 4.7.1 package). The scanner's match on
  version is right to flag it. The exposure is broader than the CVE text, and the mitigation covers
  it unchanged: with `attributionControl: false` no attribution string reaches `innerHTML`, sanitised
  or not.

**Decision.**
1. The Glass moves to `maplibre-gl` `>=6.4.1 <7` and stays on Sigma 3, keeping its own binding.
   `@sigma/layer-maplibre` and `@sigma/edge-curve` leave `apps/workspace/package.json`, and the
   CVE-2026-85061 entry leaves `.trivyignore`, in the same change.
2. `attributionControl: false` and the attribution drawn as text stay. The trust boundary is now the
   library's allow list, and the product's own text node needs no trust in it.
3. The 6.x worker is self-hosted. The Glass calls `setWorkerUrl` with the URL of the worker file its
   build emits, so a strict policy needs `worker-src 'self'` and no `blob:`. A Vite build left to
   MapLibre's default emits no worker file and points at `/assets/maplibre-gl-worker.mjs`, which does
   not exist.
4. WebGL 2 is required (6.0.0 dropped WebGL 1). Where it is missing, the `Map` constructor throws
   `GPUInitializationError`, and the Map view shows a message saying so instead of a blank panel.
5. Sigma 4, and with it `@sigma/layer-maplibre` 4.x, is not a condition of this amendment. The owner ruled on
   18 November 2026 (`process/lanes/v062/RULINGS.md`) that the GOV.UK tree's graph and map modules start on Sigma 4,
   and that moving today's workspace to Sigma 4 is decided only after the graph module has met the budget on it. The 4.x binding makes the map non-interactive and syncs one way, from
   sigma to the map. Amendment 1's threat model needs no change: it named the one input, and the
   control that reads it stays off.

**Tests, named before the change (`CLAUDE.md` rules 12 and 15).**
- `make trivy` with `maplibre-gl` 4.7.1 left in the lockfile and the `.trivyignore` entry removed:
  red. With 6.x in the lockfile: green.
- `keyboard/map-view.spec.ts`, "MapLibre's attribution control is never drawn": unchanged. It must be
  shown red again on 6.x with `attributionControl: true` planted.
- New, in the build's own tests: the production build contains the worker file, and the URL the page
  passes to `setWorkerUrl` resolves to it. Red on a build without the `setWorkerUrl` call.
- New: the Map view under a WebGL-less context shows the message. Red with the handler removed.
- The performance gate (`spec/02_GLASS_FRONTEND.md` §5, `perf/perf.spec.ts`) and every map spec in
  `keyboard/` pass before and after, against the same fixture.

**Not checked.** No browser run on 6.x: tiles, PMTiles through `addProtocol`, the site image source,
the camera across a resize (ADR-086 Amendment 1's two tests), and the frame-rate budget are all
unmeasured on 6.x. The type-check passes (the whole of `apps/workspace/src` against 6.19.0, with
`MapView.tsx:30` changed to a namespace import). The Vite build passes, apart from the worker file.

**Also found, and not decided here.** `00_ARCHITECTURE.md` says rotation and pitch are needed for site
geospatial. Both the product's binding and the 4.x binding pin pitch to 0 and turn sigma's camera
rotation off. That was true before this amendment and stays true after it.
