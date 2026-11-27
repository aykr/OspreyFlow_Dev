# Slice GG5f · GG5 · The graph drawn over the map on the GOV.UK pages: a saved view's located nodes and their links by Sigma 4 through `@sigma/layer-maplibre` 4.0.1, merged after WS4b (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** Release scope A-full (D273). **It draws with Sigma 4, so it merges only after WS4b** (ADR-152 decision 9:
"No other page that draws with Sigma 4 merges until WS4 is in"); it may be written meanwhile. It needs GG5b (the map
module) and GG2b (the graph module drawing a saved view) built. **WS4b stopped on its away round** at the canvas look
and the budget (`away/WS4b:OspreyFlow_Build/process/lanes/v062/away/WS4b_AWAY_REPORT.md`, questions 1 and 8, the
owner's), so this slice's merge waits on those answers too.

**Where it comes from.** `spec/02_GLASS_FRONTEND.md` §3.5 (:2044-2047): "MapLibre GL JS with `@sigma/layer-maplibre`,
so the graph draws over the map in the same projection and a node with coordinates sits where it belongs". ADR-152
decision 9 (`spec/06_DECISIONS.md` about 41091-41116): the new modules use Sigma 4.0.x "with `@sigma/layer-maplibre`
4.0.1 and `maplibre-gl` `>=6.4.1 <7`"; "the canvas-look comparison, run on the React canvas and the `pages` graph module
once both are on one version, has no accepted-differences list beyond its pixel tolerance". The plan's row GG5f
(`drafts_2026-11-26/CHAIN_PLAN.md:94`). GG5b's question 2 (ruled (a)): GG5b draws circles; the Sigma look over the map
is this slice's.

## What exists today (read on `origin/main` at `7f4f9554a` and on `away/WS4b`; re-read, lines move)

- **The React map today** binds Sigma 3 to MapLibre with a local port of the layer (`apps/workspace/src/map/sigmaMaplibreLayer.ts`,
  175 lines; `MapView.tsx:382`, `bindMaplibreLayer(sigma, { mapOptions })`), which hard-codes an outside default style
  (`sigmaMaplibreLayer.ts:81`), locks pitch (:84-85) and rotation (:91-92).
- **On `away/WS4b`** (built, not merged; stopped): the port is removed and `@sigma/layer-maplibre` 4.0.1 imported
  (`MapView.tsx`, the import's comment: "flips y by a constant … frames the graph in a fixed Mercator box … fixes pitch
  at 0 and turns rotation off itself"). The round found and fixed, each red first (report, case 7):
  - **a marker a hundred times its size**: the package frames the graph in the world's Mercator box (a camera ratio
    near 1e-4), so Sigma's size-by-zoom inflated it; fixed by `MAP_SIGMA_SETTINGS` (`itemSizesReference: "screen"`,
    `zoomToSizeRatioFunction: () => 1`, `labelRenderedSizeThreshold: 5`);
  - **each marker up to 85 px from its place**: the camera's ease was drawn before the map loaded, and 4.0.1 follows
    the camera only after; fixed by `layer.map.once("load", () => sigma.scheduleRender())`, proved by a case that
    reads each marker's colour at MapLibre's projection of its place;
  - **WebGL 2** is needed by both libraries; the view says so in words where it is missing (`webgl2Available`).
  - The comparison's map scene is red at 0.84% (the report's figures), part of question 1's look.
- **The page service's allow-list.** On `origin/main`, `ALLOWED_DRAWING` is empty and a drawing import is refused
  unless "a slice that draws allows it by name" (`apps/pages/scripts/assets.mjs:31-33`, :182-186). On `away/GG2a`,
  `DRAWING_MODULES = { graph: ["sigma"] }` (`assets.mjs:44`), checked by **the import's first path segment**
  (`allowedDrawing.includes(args.path.split("/")[0])`, :195). **For a scoped package that segment is `@sigma`**, so
  allowing `@sigma/layer-maplibre` by that rule would allow every `@sigma/*` package (question 4).
- **Pins.** `away/GG2a` pins `sigma` 4.0.6 and `graphology` 0.26.0 exactly in `apps/pages/package.json`; `away/GG5a`
  pins `maplibre-gl` 6.19.0 and `pmtiles` 4.5.0; `away/WS4b`'s workspace takes `@sigma/layer-maplibre` `^4.0.1`. I20's
  check (`OspreyFlow_Core/scripts/same_drawing_versions_check.mjs`, with `tests/glass_trees/test_same_drawing_versions.py`) **is on `away/WS4a` and `away/WS4b`, not on `origin/main`**; it holds the two front ends to one resolved version.
- **`spec/02` §5 has no figure for a map**, only the canvas's; nothing measures the graph layer's frame time.

## Acceptance (red before, green after)

Scenario **MP**'s graph-layer rows, written first; the map page's browser spec (each located node drawn at MapLibre's
projection of its place, links drawn between them, the policy clean), red on GG5b's circles page, green after; the
canvas-look comparison's map scene run on the `pages` map module beside the React Map view, within the comparison's
tolerance; I20 green with the window empty.

## Questions for the owner (the proposal first)

1. **What replaces GG5b's circles.** (a) **The graph layer replaces the circles on the case map**: the view's located
   nodes as Sigma draws them in the workspace, with the links between two located nodes; a link with an unlocated end
   is not drawn on the map and is listed in the page's links table, which says so (rule 2). (b) Both, the circles kept
   behind a switch.
2. **One set of settings (I11).** (a) **`MAP_SIGMA_SETTINGS` (WS4b's) moves to `glass-shared`** as plain data, read by
   both front ends; the settings read-back case runs on the page module too (WS4b's lesson: Sigma 4 reads its settings
   only where it is given them). (b) A copy in the page module. **Not proposed** (I11).
3. **The look.** (a) **The comparison's map scene, on the same fixture, judged at the comparison's own tolerance**, once
   the owner has ruled WS4b's question 1 (the look); no accepted-differences list (decision 9). (b) No comparison for
   the map.
4. **The allow-list for a scoped package.** (a) **The check reads a scoped import's first two segments**
   (`@sigma/layer-maplibre`), so `DRAWING_MODULES.map` names exactly `["maplibre-gl", "sigma", "@sigma/layer-maplibre"]`,
   with a test that the map module importing `@sigma/node-image` is refused; red first on today's first-segment rule.
   (b) Allow `@sigma` whole. **Not proposed.**
5. **The pin.** (a) **`@sigma/layer-maplibre` pinned exactly to the workspace's resolved 4.0.1** in `apps/pages`, and
   I20's check extended to it. (b) A range.
6. **Turning and tilting.** The package locks both (GG5e2). (a) **On a map with the graph layer, no turn or tilt is
   offered, and the page says so**; a site plan's page without the layer keeps GG5e2's controls. (b) The layer taken
   off while the map is turned.
7. **The budget.** `spec/02` §5 names no map figure. (a) **No new gate**: the builder measures the first frame and a pan
   on the largest synthetic view and records them; a gate would be a `spec/02` §5 change (owner, a CI gate). (b) A gate
   now (owner).
8. **Scripts off.** (a) **GG5b's places table and a links table** (each link's two ends by name and its type), with a
   link to the view's Matrix (GG2d). (b) The places table only.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A view with 12 located nodes and 9 links among them | 12 nodes, each drawn at MapLibre's projection of its place (WS4b's colour read at each place); 9 links | the camera's ease drawn before the map's `load` (WS4b's defect, replanted) |
| 2 | Marker size at the fitted view and after zooming in two steps | the same screen size | `zoomToSizeRatioFunction` left to Sigma's default |
| 3 | The settings read back from the live renderer | equal to `MAP_SIGMA_SETTINGS` | one setting given at the top level of the constructor's options (WS4b's case 4 plant) |
| 4 | A link with one end unlocated | not drawn; listed in the links table as "one end has no map position" | the link dropped from both |
| 5 | Readiness | Sigma 4's readiness mark (GG2a's) and the map's `idle`, both | the check on `idle` alone |
| 6 | No WebGL 2 | "This map needs a browser with WebGL 2"; the tables whole | a blank map |
| 7 | The allow-list (question 4) | the map module may import the three named packages; `@sigma/node-image` is refused in words | today's first-segment rule (the plant passes: red) |
| 8 | I20 | one `sigma`, one `@sigma/layer-maplibre`, one `maplibre-gl` across both workspaces; the window empty | `@sigma/layer-maplibre` 4.0.0 pinned in `apps/pages` |
| 9 | The policy (I2) and other origins (I3) | no violation; no request but the page's own (the package's default style never fetched) | the map made without the page's style, so the package's default address is asked |
| 10 | The look (question 3) | the map scene within the comparison's tolerance against the React Map view | a link colour from another token |
| 11 | Turning (question 6) | no turn or tilt offered; Shift and the arrows do not turn | GG5e2's controls shown with the layer bound |
| 12 | Scripts off | the places and links tables, whole | the links table drawn only by the module |
| 13 | Two readers of different clearance | each map and table only what GG2b's read sent them | at the page's call site: the map page's render cache keyed by the case and view, not the session (the second reader served the first's graph), or the first reader's token reused for the second's read |
| 14 | A view over the cap | GG2b's three options in words; no map drawn | the first N nodes drawn (rule 2) |
| 15 | Keyboard | a node reached and its name said, and the map's own controls (rule 13); ids in the page's map registry | a node reachable only by pointer |

## Waits on

GG5b and GG2b built; **WS4b merged** (decision 9), which waits on the owner's WS4b questions 1 (the look) and 8 (the
budget); **WS4b question 3**, a map marker's fixed size, which case 2 asserts, and **WS4b question 2**, WebGL 2 as the
Glass's requirement, which case 6 asserts (`away/WS4b:…/WS4b_AWAY_REPORT.md:118-126`); **WS4a merged**, since I20's
check (case 8) is not on `origin/main` until it does; GG2d for the links table's link to the Matrix (question 8).

## Files touched

`spec/08` (MP's rows); `spec/02` §3.5 (the page service's graph layer); `apps/pages/modules/map/` (the layer bound);
`apps/pages/scripts/assets.mjs` (`DRAWING_MODULES.map`, the scoped-name rule) and its test; `apps/pages/package.json`
and the lockfile (`@sigma/layer-maplibre` 4.0.1 exactly); `scripts/same_drawing_versions_check.mjs` (the package
added); `packages/glass-shared/src/map/` (`MAP_SIGMA_SETTINGS`, moved) and `apps/workspace/src/map/MapView.tsx` (its
import); the comparison's map scene for the page module (`apps/workspace/keyboard/canvasCompare.ts`'s scene list or the
page's twin); `tree-govuk/` (the links table); the tests above.

## Checks (frozen when cut)

GG5b's list, with `make licence-check`, I20's check and its plant, the canvas-look comparison, the settings read-back
spec, and the workspace's unit and keyboard suites (the moved constant).

## Out of scope

Editing the graph on the map (GG2g's actions); the live working set on the map (GG2e's stream); the heat layer under it
(GG5c); turning a map that draws the graph (question 6); any Conduit change.
