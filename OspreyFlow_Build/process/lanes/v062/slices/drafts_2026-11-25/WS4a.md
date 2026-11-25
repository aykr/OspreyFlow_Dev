# Slice WS4a · WS4 · Before the React workspace moves to Sigma 4: the canvas-look comparison, the version window file and its check, and readiness signals that do not name a Sigma 3 canvas, all on Sigma 3, red first (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. No row in `slices.tsv`; no builder starts from this paper.

**Where WS4 comes from.** ADR-152 decision 9 (`OspreyFlow_Build/spec/06_DECISIONS.md` about lines 41091 to 41116) says
that if R4's first step (GG2a) meets the budget, "the React workspace moves to Sigma 4 at once, as its own slice,
**WS4**. WS4 is held to the React workspace's own whole suite, its budget and the canvas-look comparison. WS4 ports
`GlassCanvas.tsx` and the version-bound files of decision 6 to Sigma 4." Further: "**R4's budget proof and WS4 come
first.** No other page that draws with Sigma 4 merges until WS4 is in"; the difference is "written in
`apps/pages/VERSION_WINDOW.yaml` with the day it opened", and "a release is not cut while that file lists anything".
The correction of 19 November (about line 40973) and D47 (about line 40972) say the same. Invariant I20 (about line
41242): "Both front ends resolve the same versions of `sigma`, `@sigma/*`, `maplibre-gl` and `graphology`, except a
difference written in `VERSION_WINDOW.yaml`" (`scripts/same_drawing_versions_check.mjs`). **WS4 does not start until
GG2a has measured, and GG2a's §5 figures are taken on the owner's Mac on his return** (`slices/GG2a.md`). This first
slice is proposed so that WS4's three gates exist and have been shown red before any line of the port is written.

**Question 0, rechecked against the plan's row (the owner, 25 November 2026, later the same day):** "**WS4: Today's
React workspace moves to Sigma 4**", which **needs GG2**. **The reading holds.** **A conflict to resolve: "needs GG2"
cannot mean the whole of GG2.** Decision 9 (about lines 41101 to 41102) and the correction of 19 November (about line
40973) say that no other page drawing with Sigma 4 merges until WS4 is in. GG2b to GG2d draw with Sigma 4, so they wait
for WS4 (NEXT_BATCH question 5). If WS4 also waited for all of GG2, neither could merge. **Proposed reading: "needs
GG2" means GG2a, the budget page and its measurement on the owner's Mac.** **Changed:** question 2's proposal now
follows the plan's "needs" (after GG2a), and starting beside GG2a becomes the owner's exception.

## What exists today (read on 25 November 2026 at `4f77858a5`; re-read, lines move)

- **The pins.** `OspreyFlow_Core/apps/workspace/package.json`: `@sigma/export-image`, `@sigma/node-border` and
  `@sigma/node-image` at `^3.0.0` (:23 to :25), `graphology` `^0.26.0` (:31), `maplibre-gl` `^6.4.1` (:36) and
  `sigma` `^3.0.0` (:41). The root lockfile `OspreyFlow_Core/package-lock.json` resolves `@sigma/*` 3.0.0 (about lines
  1639, 1651, 1660), `graphology` 0.26.0 (about 3755), `maplibre-gl` 6.19.0 (about 4754) and `sigma` 3.0.3 (about
  5941). `packages/glass-shared/package.json:16` pins `graphology` `^0.26.0`. **`apps/pages/package.json` pins none of
  them** (GG2a adds Sigma 4 there, pinned exactly).
- **The version-bound files** (decision 6's table, about line 41061), with line counts as read today:
  - `src/canvas/GlassCanvas.tsx` (4,104 lines; the decision record says 4,078). It uses `Sigma` (:99),
    `@sigma/node-border` and `@sigma/node-image` (:93-94), and `sigma/rendering`'s `EdgeLineProgram`,
    `EdgeRectangleProgram`, `NodeCircleProgram` and `createNodeCompoundProgram` (:97). It registers
    `nodeProgramClasses` and `edgeProgramClasses` (:1703-1715), a `nodeReducer` (:1729) and an `edgeReducer` (:1778),
    and calls `graphToViewport` (:1005, :1885), `getCamera` (:1154, :1159), `refresh` (:1142, :1153) and
    `on("downNode")` (:1938).
  - `src/canvas/dottedEdgePrograms.ts` (217): `EdgeLineProgram` and `RenderParams` (:16-24); `DottedEdgeProgram`
    (:197), its arrowed variant (:201) and `DashedEdgeProgram` (:208).
  - `src/canvas/labelStyle.ts` (105): the label and hover drawing types (:8).
  - `src/canvas/communityLinkLayer.ts` (103): the `Sigma` type (:6).
  - `src/map/sigmaMaplibreLayer.ts` (175): `maplibre-gl` (:12) and the `Sigma` type (:13).
  - `src/export/chartExport.ts` (90): the `Sigma` type (:28).

  Fifteen source and harness files import `sigma` or `@sigma/*` directly. Besides the six above, these include the
  canvas overlays (`BubbleOverlay`, `CommunityBoxOverlay`, `CommunityHullOverlay`, `JudgementBadgeOverlay`,
  `PreviousPositionsOverlay`), `src/ingest/map/MapCanvas.tsx`, `src/map/MapView.tsx`, `src/reports/alertBadges.tsx`
  and `keyboard/map-canvas-harness.tsx`. **Decision 6 lists six version-bound files. The port touches at least
  fifteen.**
- **Tests that name a Sigma 3 canvas element.** Sigma 4 has no `canvas.sigma-nodes` (decision 9).
  - The workspace's own CI budget gate: `perf/perf.spec.ts:110` locates `canvas.sigma-nodes`, and its readiness hook
    in `perf/harness.tsx:78` and :86 waits for `canvas.sigma-nodes` to appear before it sets
    `window.__PERF__.readyAt`, which `perf.spec.ts` waits on (:43, :89). Its gates are a first frame under 30,000 ms
    (:74) and a sweep under 3,000 ms a frame (:176), on the 50,000 / 250,000 fixture (`perf/fixture.ts:7-8`).
  - `keyboard/link-selection.spec.ts:142` reads `canvas.sigma-labels`.
  - `keyboard/canvas-look.spec.ts:201` hides `.sigma-nodes` and `.sigma-labels`.
  - `perf/community-links.spec.ts:15` (the spec that was red in the parked attempt).

  **On Sigma 4, the budget gate's readiness would never fire** (a 60-second timeout, not a figure), so the port cannot
  be judged by the gate it is held to until the signal is its own.
- **"The canvas-look comparison" does not exist as a comparison.** `keyboard/canvas-look.spec.ts` (272 lines) reads
  painted pixels for particular properties: a node 14 pixels across at 100% (:54, 12 to 17), a click beside a node
  (:67), route degree marks (:106), the 16 px grid (:120), the toolbar (:145, :174), and links plainly drawn when
  zoomed out, on wheel and pinch (:224, :237, :255). **No test compares a whole rendered canvas against a reference
  within a pixel tolerance.** Searches for `toHaveScreenshot` and `screenshot(` find only contrast plants
  (`a11y/plants/*.plant.ts`) and deck captures that assert nothing (`deck-capture/*.capture.ts`). Decision 9 relies on
  "the canvas-look comparison ... no accepted-differences list beyond its pixel tolerance".
- **Not on main:** `apps/pages/VERSION_WINDOW.yaml` and `scripts/same_drawing_versions_check.mjs` (I20).
  `scripts/version_isolation_check.mjs` (I13) exists (`OspreyFlow_Core/scripts/`, header :1-22).
- **The parked attempt** (`OspreyFlow_Build/process/HANDOVER_2026-10-20.md` about lines 27 to 45): the branch `sigma-4`,
  draft PR #1, ADR-118 on that branch only (`spec/06` about line 14203 calls it "the parked Sigma 4 record"). CI run
  39470175438 gave a first frame of 27.0 s (gate 30) and a sweep of 9,357 ms a frame (gate 3,000), with
  `community-links.spec.ts` red. "Sigma 4 hands every link to its GPU program whatever its visibility (`processEdges`
  ...), where Sigma 3 skipped hidden links, so hiding links, ADR-119's lever, buys Sigma 4 almost nothing." The way
  back, leaving undrawn links out of the program, "needs its own ADR, measured on CI first". ADR-119 is at `spec/06`
  about line 14199 (above 10,000 links, one link per pair of communities when zoomed out; above 10,000 nodes, dots).

## Questions for the owner (the proposal first)

1. **What WS4's first slice is.** (a) **WS4a, with no version change: the three gates WS4 is held to, built on Sigma 3
   and shown red,** before the port starts. They are the canvas-look comparison, the version window file with I20's
   check, and readiness signals that name no Sigma 3 element. WS4b is the port itself. (b) One slice that ports and
   builds its own gates, which would judge the port with gates written alongside it, the failure CLAUDE.md rule 15
   describes.
2. **When WS4a may start (changed after the plan's row was given).** (a) **After GG2a has merged, as the plan's "needs
   GG2" reads under question 0's proposed reading.** It does not wait for the owner's Mac figures, since WS4a changes no
   version. WS4b, the port, waits for those figures and a passed budget (decision 9). (b) An exception for the owner
   alone to give: start now, beside GG2a. WS4a changes nothing visible, and it is needed whether or not Sigma 4 passes,
   because decision 9 runs the comparison "on the React canvas and the `pages` graph module once both are on one
   version", which includes a Sigma 3 fallback. The first draft proposed this.
3. **What the canvas-look comparison is.** (a) **A Playwright spec in `apps/workspace/keyboard/` (named
   `canvas-compare.spec.ts`).** It draws a fixed set of synthetic scenes, compares each against reference images kept
   in the repository within one stated pixel tolerance, in Chromium, with the fonts fixed, and keeps no
   accepted-differences list. The scenes: plain, dotted, dashed and arrowed links (`dottedEdgePrograms.ts`); node
   borders and images (`@sigma/node-*`); labels and hover (`labelStyle.ts`); community links when zoomed out
   (`communityLinkLayer.ts`, ADR-119); a selected node and link; the map layer (`sigmaMaplibreLayer.ts`, on GG6's tile
   fixture); and an exported PNG (`chartExport.ts`). The references are made once on Sigma 3 by a named command, and
   the tolerance is set from three runs of Sigma 3 against itself. (b) A comparison of numbers only (sizes, colours at
   points), extending `canvas-look.spec.ts`. It is cheaper, but it would not see a dashed link drawn solid.
4. **Where the references are made.** (a) **In CI's own browser image (software rendering)**, so the comparison is a
   gate there. The owner's Mac makes its own set only if he wants a local check. (b) On the owner's Mac. That cannot
   be a CI gate, because pixels differ between GPUs.
5. **The version window file and I20's check.** (a) **`apps/pages/VERSION_WINDOW.yaml`**, empty (a list with no
   entries) on main, with `scripts/same_drawing_versions_check.mjs`. The check reads the resolved versions of `sigma`,
   `@sigma/*`, `maplibre-gl` and `graphology` for both workspaces from `package-lock.json` (the resolved tree, not the
   ranges), fails on any difference the file does not list (with the day it opened), and **fails a release while the
   file lists anything** (through `release_green.py` or the release workflow, as an owner's diff). It is shown red on
   three plants: a planted difference, a listed difference at release, and the shape the lock really has for a nested
   duplicate (`node_modules/x/node_modules/sigma`). (b) The check in WS4b with the port. That leaves GG2a's Sigma 4 pin
   in `apps/pages` (which opens the window) with no check that the window is written down.
6. **The readiness signals.** (a) **The canvas sets its own ready mark** (a `data-ready` attribute on the canvas's
   application element, set by `GlassCanvas.tsx` after its first render), and `perf/harness.tsx`, `perf.spec.ts` and
   the three keyboard specs read that mark or the canvas's role in place of `.sigma-*` class names. Each is shown red
   first on a selector that never matches (I12's red for the page module, applied to the workspace's own gate). This
   is behaviour-preserving on Sigma 3. (b) Leave them to WS4b.
7. **Sigma 4's version.** (a) **The same exact version GG2a pins** (the newest 4.x at least 14 days old). If
   `@sigma/node-border`, `@sigma/node-image` or `@sigma/export-image` has no release for that line, WS4b stops and the
   owner is told. Decision 9 names only `@sigma/layer-maplibre` 4.0.1. (b) The newest at WS4b's start, which could
   differ from GG2a's.
8. **The ADR-119 problem.** (a) **WS4b does not start until GG2a's figures are in.** If GG2a misses the budget, nothing
   moves (decision 9). If GG2a passes only with undrawn links left out of the program, that needs its own ADR (as
   NEXT_BATCH question 4 proposed), and WS4b follows that ADR. (b) WS4b ports as written and measures afterwards, as
   the parked attempt did.

## The table of cases for WS4a (each red first; planted faults at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Each scene against its reference, on Sigma 3 | within the tolerance, in Chromium | the dotted program swapped for `EdgeLineProgram` at `GlassCanvas.tsx`'s program table (a dashed link drawn solid): red on the dotted scene only |
| 2 | A label style change | red on the label scene | `labelStyle.ts`'s font size changed by 1 px |
| 3 | The community links scene zoomed out | within tolerance | ADR-119's community layer turned off at its real switch |
| 4 | The map layer scene | within tolerance | the layer's camera sync offset by a pixel at `sigmaMaplibreLayer.ts` |
| 5 | The tolerance itself | set from three Sigma 3 runs against the references, recorded with the machine | a tolerance of 100% (anything passes): the check refuses a tolerance above a stated ceiling |
| 6 | The reference-making command | refuses to run with no reason given and records who and why in the commit | run with no reason |
| 7 | I20, the same versions | green on main (empty file, same resolved versions) | `sigma` resolved differently in `apps/pages` with the file empty: red, naming the package and both versions |
| 8 | I20, a listed window | green while listed, with its day | the entry with no day: refused |
| 9 | I20, at release | the release check refuses while the file lists anything | a listed entry on a release commit |
| 10 | I20, a nested duplicate | red | the lockfile's nested `node_modules/x/node_modules/sigma` shape, with another version |
| 11 | The budget gate's readiness | `readyAt` set from the canvas's own mark; the figure unchanged within the run-to-run spread on Sigma 3 | the selector pointed at a mark never set: red (never ready), shown first |
| 12 | The three keyboard specs | green on the role or mark, with no `.sigma-*` class name left in any spec | the class names left in one spec, caught by a check that fails on `sigma-` in `keyboard/` and `perf/` |
| 13 | Nothing visible changed | the whole workspace suite and the budget, before and after on the same machine (I11's method) | none: an equality, run once |

## Checks (for WS4a; frozen when cut)

The workspace's whole suite (vitest, keyboard, a11y, perf, as CI runs them); the new comparison spec; the I20 check and
its own red-then-green test; `node scripts/version_isolation_check.mjs`; `node scripts/no_react_check.mjs`;
`npm run lint` and `npm run typecheck` in `apps/workspace`; `tests/test_doc_citations_check.py`;
`make -C OspreyFlow_Build design-check` (the canvas's look); the cheap checks of 20 November. **Wiring the I20 check
and the comparison into `make ci` and `ci.yml` is an owner's diff** (protected files), written once each is shown red.

## Out of scope

The port to Sigma 4 (WS4b); any Sigma 4 package in `apps/workspace`; GG2a's module and fixture move (GG2a's); the
ADR for leaving undrawn links out of the program (it waits for GG2a's figures); any change of what the canvas looks
like; the `pages` graph module's side of the comparison (once it exists, GG2's later slices run the same scenes
against it).
