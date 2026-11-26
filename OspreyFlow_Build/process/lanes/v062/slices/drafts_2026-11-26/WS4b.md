# Slice WS4b · WS4 · The React workspace moves to Sigma 4: `GlassCanvas.tsx`, the version-bound files and every other importer, judged by WS4a's three gates, and the version window closed in the same merge (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** ADR-152 decision 9 (`spec/06_DECISIONS.md` about lines 41091 to 41116): "If it meets the
budget, the React workspace moves to Sigma 4 at once, as its own slice, **WS4**. WS4 is held to the React workspace's own
whole suite, its budget and the canvas-look comparison. WS4 ports `GlassCanvas.tsx` and the version-bound files of
decision 6 to Sigma 4." "No other page that draws with Sigma 4 merges until WS4 is in, the Studio's graph preview
included." ADR-002 Amendment 1 (about 41297 to 41325). WS4a (drafted 25 November) builds the three gates on Sigma 3 and
shows each red; **this slice is the port they judge.**

**It starts only when all of these hold:** WS4a merged; GG2a's question 1 answered "go on with Sigma 4"; the owner's Mac
figures in (`slices/GG2a.md`, the 18 November ruling); and question 2 below answered.

## What exists today (read on `origin/main` at `042c882f2` and on `away/GG2a`; re-read, lines move)

- **The pins and what resolves.** `OspreyFlow_Core/apps/workspace/package.json`: `sigma` `^3.0.0` (:41),
  `@sigma/export-image`, `@sigma/node-border`, `@sigma/node-image` `^3.0.0` (:23-25), `graphology` `^0.26.0` (:31),
  `maplibre-gl` `^6.4.1` (:36). The lockfile resolves `sigma` 3.0.3 and each `@sigma/*` 3.0.0
  (`OspreyFlow_Core/package-lock.json` about 1639, 1651, 1660, 5941). **On `away/GG2a`, `apps/pages/node_modules/sigma`
  resolves 4.0.6** (its lockfile, about line 79), nested beside the workspace's 3.0.3: the window decision 9 describes.
- **The `@sigma/*` plugins' peer ranges are `>=3.0.0-beta.17` and `>=3.0.0-beta.10`** (the lockfile, about 1656 and
  1665). npm would install them beside Sigma 4 without a word, **but a peer range is not proof that a program written
  for Sigma 3's program interface draws under Sigma 4's.** Whether a 4.x of each exists was not read (no network in this
  session).
- **What imports Sigma in the workspace** (the scout listed 15 import lines in 13 files; **a recount finds 20 import statements in 15 files**, adding the value
  imports at `GlassCanvas.tsx:97-98` (`sigma/rendering`, `sigma/utils`), `dottedEdgePrograms.ts:17-24` and
  `labelStyle.ts:8`; the builder recounts):
  - values: `src/canvas/GlassCanvas.tsx:93` (`@sigma/node-border`), :94 (`@sigma/node-image`), :99 (`sigma`);
    `src/ingest/map/MapCanvas.tsx:13` (**the Studio's graph preview**, which decision 9 names); `src/map/MapView.tsx:39`;
  - types only: `BubbleOverlay.tsx:2`, `CommunityBoxOverlay.tsx:2`, `CommunityHullOverlay.tsx:2`,
    `JudgementBadgeOverlay.tsx:2`, `PreviousPositionsOverlay.tsx:6`, `communityLinkLayer.ts:6`,
    `export/chartExport.ts:28`, `map/sigmaMaplibreLayer.ts:13`, `reports/alertBadges.tsx:7`,
    `keyboard/map-canvas-harness.tsx:5`.
  - **`@sigma/export-image` is declared but imported nowhere** (`chartExport.ts` imports only Sigma's type).
  - **`sigmaMaplibreLayer.ts` is a local port of `@sigma/layer-maplibre` 3.0.0** (its header, :1-3), not a dependency;
    it sets `minPitch: 0` and `maxPitch: 0` (:84-85) and turns rotation off (:92). Decision 9 names
    `@sigma/layer-maplibre` 4.0.1 for the page module.
- **The custom programs.** `src/canvas/dottedEdgePrograms.ts` (217 lines) builds five programs, `DottedEdgeProgram`, its
  arrowed variant, `DashedEdgeProgram`, `DashedArrowProgram` (:211) and `SolidArrowProgram` (:217), on Sigma 3's
  `createEdgeClampedProgram` (:154), cast to `typeof EdgeLineProgram` (:16-24). Decision 9 says the page module uses Sigma
  4's "built-in dashed and curved links … not ported program by program". `GlassCanvas.tsx` registers
  `nodeProgramClasses` and `edgeProgramClasses` (:1703-1715), a `nodeReducer` (:1729) and an `edgeReducer` (:1778).
- **What GG2a learned that bears on the port** (its report, "A correction the owner should read first"): **Sigma 4 reads
  its settings in `options.settings` and ignores them at the top level without a word**; GG2a's first five runs measured
  Sigma's defaults for that reason, and the fix was a test that reads `hideEdgesOnMove` and `renderLabels` back from the
  live renderer. With the settings in place, the page module's sweep was 1,184 to 2,516 ms a frame against the
  workspace's 3,000 gate; the parked October attempt's 9,357 ms (`HANDOVER_2026-10-20.md` about 27 to 45) does not
  recur there.
- **Not on main yet** (WS4a's): `apps/pages/VERSION_WINDOW.yaml`, `scripts/same_drawing_versions_check.mjs`, the
  canvas-look comparison, the readiness marks.

## Acceptance (red before, green after)

On the port's branch, **before any source change, the version bump alone is shown red** by WS4a's gates (the
comparison, the readiness mark or a typecheck), recorded; after the port: WS4a's canvas-look comparison within its
tolerance on every scene, I20 green with `VERSION_WINDOW.yaml` **empty**, the workspace's budget gate green three runs of
three on CI's own runner, and the workspace's whole suite green.

## Questions for the owner (the proposal first)

1. **One merge, not two.** (a) **WS4b is one slice merged once**, worked in rounds (round 1: the canvas, its programs,
   reducers and labels; round 2: the overlays, the map layer, the Studio's preview and the export; round 3: the gates),
   because one npm workspace cannot hold Sigma 3 for half its files and Sigma 4 for the other half. The chain plan's
   "split WS4b1, WS4b2" is withdrawn. (b) Two slices on stacked branches merged together.
2. **The `@sigma/*` plugins.** (a) **The builder first reads whether `@sigma/node-border` and `@sigma/node-image` have a
   4.x release at least 14 days old (GG2a's rule); if either has none, it stops and brings the options** (draw borders
   and images with Sigma 4's own node programs, or keep a local port as for the map layer); `@sigma/export-image` is
   removed from `package.json`, since nothing imports it. (b) Keep the 3.0.0 plugins on the strength of their peer
   range. **Not proposed:** a peer range is not proof.
3. **The dotted and dashed links.** (a) **Sigma 4's own dashed links, as decision 9 says for the page module**, with
   the canvas-look comparison as the judge; `dottedEdgePrograms.ts` goes only if the comparison's dotted and dashed
   scenes pass within the tolerance; if Sigma 4's built-in look differs beyond it, the builder stops (the comparison has
   no accepted-differences list). (b) Port the custom programs.
4. **The map layer.** (a) **`@sigma/layer-maplibre` 4.0.1, as decision 9 names**, in place of the local port, with
   `minPitch` and `maxPitch` 0 and rotation off as today (rotation and pitch are GG5e's); the map scene of the comparison
   is its judge. (b) Port the local copy.
5. **Settings read back.** (a) **A test reads every setting the workspace passes (`hideEdgesOnMove`, `renderLabels`,
   the label and hover settings) back from the live Sigma instance**, as GG2a's readiness case does, red with one setting
   planted at the top level. (b) Rely on the typecheck. **Not proposed:** GG2a's typecheck caught it only once the module
   was typed for Sigma 4.
6. **Where the budget is judged.** (a) **CI's runner, three runs of three, and the owner's Mac once for §5's own
   numbers**, as for GG2a; if CI misses, stop and bring the figures (the ADR for leaving undrawn links out of the program,
   WS4c, is drafted then, not before). (b) This server's figures. **Not proposed:** GG2a showed another account's load
   moved the first frame by 17% to 48% (24,675 ms quiet against 28,961, 33,989 and 36,488).
7. **The window.** (a) **The merge empties `VERSION_WINDOW.yaml`** (WS4a's file, opened when GG2a merged), and I20's
   check green with it empty is a condition of the merge; the release check (RL2) then sees nothing listed. (b) A follow-up
   slice closes it.
8. **The ADR-119 lever** (above 10,000 links, one per pair of communities when zoomed out). (a) **Kept as it is; the
   community-links scene and `perf/community-links.spec.ts` (red in the October attempt) are its judges.** If either is
   red after the port, that is WS4c's ADR, the owner's. (b) Redesigned now.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | The version bump alone, before any port | red on the typecheck or the comparison or the readiness mark, recorded | none: this is the slice's first red |
| 2 | Each canvas-look scene (WS4a's) | within the tolerance on Sigma 4 | a dashed link drawn solid (the dashed style left off one link type) |
| 3 | Labels and hover | within tolerance | the label setting at the top level of the options (ignored by Sigma 4) |
| 4 | Settings read back (question 5) | every setting equal to what the workspace passed | one setting planted at the top level |
| 5 | Node borders and images | within tolerance | the border program left unregistered |
| 6 | Community links zoomed out (ADR-119) | within tolerance; `community-links.spec.ts` green | the community layer's switch off |
| 7 | The map layer | within tolerance; no pitch, no rotation | the layer's rotation lock (`sigmaMaplibreLayer.ts:92`'s equivalent in the package) turned off at the call site (the package's own `minPitch`/`maxPitch` are already 0, so a pitch plant could not go red) |
| 8 | The Studio's graph preview (`MapCanvas.tsx`) | its own tests green; drawn on Sigma 4 | the preview's own settings passed at the top level of the options (ignored by Sigma 4), caught by question 5's read-back |
| 9 | The budget gate, CI, three runs | first frame and sweep under the workspace's gates | none: a measurement, recorded with the runner |
| 10 | I20 with the window empty | green: one `sigma`, one of each `@sigma/*`, one `graphology`, one `maplibre-gl` across both workspaces | a nested Sigma 3 left under `apps/workspace/node_modules` |
| 11 | No Sigma 3 left | no `sigma@3` in the lockfile | the lockfile not regenerated |
| 12 | The keyboard walk and a11y | the workspace's whole keyboard and a11y suites green | none: an equality |
| 13 | Every `.sigma-*` selector gone from tests | WS4a's check green | a spec left reading `canvas.sigma-labels` |

## Files touched

`apps/workspace/package.json`, `OspreyFlow_Core/package-lock.json`; `src/canvas/GlassCanvas.tsx`,
`dottedEdgePrograms.ts` (removed or ported: question 3), `labelStyle.ts`, `communityLinkLayer.ts`, the five overlays;
`src/map/sigmaMaplibreLayer.ts` (or removed: question 4), `src/map/MapView.tsx`; `src/ingest/map/MapCanvas.tsx`;
`src/export/chartExport.ts`; `src/reports/alertBadges.tsx`; `keyboard/map-canvas-harness.tsx`; the canvas's tests;
`apps/pages/VERSION_WINDOW.yaml` (emptied); `spec/02` (the library table: Sigma 4 in both); `spec/06` only as a diff
file if a decision changes (question 2 or 3 stopping).

## Checks (frozen when cut)

The workspace's whole suite (vitest, keyboard, a11y, perf) as CI runs it; WS4a's comparison, I20 check and readiness
cases; `node scripts/no_react_check.mjs`, `version_isolation_check.mjs`; `make licence-check` (new packages); `npm run
lint` and `typecheck` in `apps/workspace` and `apps/pages`; `make -C OspreyFlow_Build design-check`;
`test_doc_citations_check.py`; the cheap checks of 20 November. Every figure is recorded with the machine it ran on
(rule 14).

## Out of scope

Any change to what the canvas does or looks like (the comparison has no accepted-differences list); rotation and pitch
(GG5e); the page module's own scenes against the workspace's (GG2b and GG2e run them once both are on one version); the
undrawn-links ADR (WS4c, only if the budget misses).
