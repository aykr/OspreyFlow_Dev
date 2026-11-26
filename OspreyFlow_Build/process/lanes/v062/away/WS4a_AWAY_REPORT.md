# WS4a away round: report (26 November 2026, the server's build account, D246)

Branch `away/WS4a` in `~/away-ws4a`, from `origin/main` at `41ed4f195`. Nothing pushed, merged or rebased; `main` not
touched. Started beside GG2a by the owner's exception (D268); every proposal of the draft taken as (a) (D268). Worked from
the draft (`drafts/2026-11-25:…/WS4a.md`), the 26 November corrections (`drafts/2026-11-26:…/INDEX.md`), CHAIN_PLAN.md's
WS4a row, `spec/06_DECISIONS.md` ADR-152 decisions 6 and 9 and invariant I20, ADR-002 Amendment 1, and `CLAUDE.md`.
**No Sigma 4 change** (that is WS4b): `apps/workspace` still resolves Sigma 3.0.3 and the lockfile is unchanged.

Every test ran through `REPO=~/away-ws4a ~/osprey-d246/d246_ns.sh` (nice 19), from `OspreyFlow_Core`, with
`OSPREY_PORTS_SLOT=21` for the Playwright runs (each run has its own network namespace, so the slot only satisfies
`lanePorts.ts`'s refusal in a linked worktree). **Every figure was taken on this server (AMD Ryzen 7 3700X, 16 CPUs,
headless Chromium, WebGL by SwiftShader), not on the owner's Mac and not on CI**, while six other agent sessions ran on
the machine (load average up to 35); the load is recorded with each run. Synthetic data only; the client is not named.

## The outcome in one paragraph

The three gates WS4 is held to exist on Sigma 3 and each has been shown red at its real call site. (1) **I20**:
`scripts/same_drawing_versions_check.mjs` with `apps/pages/VERSION_WINDOW.yaml` (empty). Green on main, red on seven
planted faults in its own code and on every planted lockfile shape, and **red on GG2a's real lockfile** until a window
entry is written. (2) **The readiness marks**: the canvas marks its own state and layers (`src/canvas/canvasMarks.ts`),
the budget gate and three specs read those marks, and no `sigma-` class name is left in the workspace (a check fails on
one). The budget gate was shown red first (never ready, a 60 s timeout, as Sigma 4 would give the old selector), then
green, with its figures within the run-to-run spread. (3) **The canvas-look comparison**: `keyboard/canvas-compare.spec.ts`
compares nine (ten with the map, see below) whole-canvas scenes against references made by a named command, within one
tolerance under a hard ceiling. Sigma 3 against its own references differed in **0 pixels** in every scene of six runs;
each planted look fault is red. **Planting found a real defect in the comparison itself**: it read colour and not
opacity, so it could not see the exported PNG's watermark at all (fixed, with its own red case).

## What to read first (for the owner)

1. **GG2a as built fails I20.** On `away/GG2a`'s lockfile (`759a45233`), `apps/pages` resolves `sigma` 4.0.6 and the
   workspace 3.0.3, and nothing lists it: `FAIL … sigma: apps/workspace resolves 3.0.3 and apps/pages resolves 4.0.6, and
   apps/pages/VERSION_WINDOW.yaml does not list it`. With the entry (below) it passes, and `--release` refuses. **Whichever
   of GG2a and WS4a merges second must write the entry** in `apps/pages/VERSION_WINDOW.yaml` (question 1):
   ```yaml
   windows:
     - package: sigma
       apps/workspace: 3.0.3
       apps/pages: 4.0.6
       opened: <the day GG2a merges>
   ```
2. **The comparison is not yet in CI, on purpose.** Its references belong to one WebGL renderer and were made here.
   It runs by `npm run test:canvas-compare --workspace apps/workspace`, kept out of `test:keyboard` (question 2). The
   I20 check and the comparison join `make ci` / `ci.yml` only by the owner's diffs in `WS4a_diffs/`.
3. **A correction to the 26 November correction.** INDEX.md says "15 import lines in 13 files; `@sigma/export-image`
   declared but imported nowhere". Both halves are wrong: **`src/export/chartExport.ts:69` imports `@sigma/export-image`
   dynamically** (`await import("@sigma/export-image")`), which a search for `from "…"` misses, and **15 files** import
   `sigma` or `@sigma/*` (21 import statements, the dynamic one and `sigma/utils` included), as the draft said. The list:
   `GlassCanvas.tsx`, `dottedEdgePrograms.ts`, `labelStyle.ts`, `communityLinkLayer.ts`, `BubbleOverlay.tsx`,
   `CommunityBoxOverlay.tsx`, `CommunityHullOverlay.tsx`, `JudgementBadgeOverlay.tsx`, `PreviousPositionsOverlay.tsx`,
   `chartExport.ts`, `MapView.tsx`, `sigmaMaplibreLayer.ts`, `ingest/map/MapCanvas.tsx`, `reports/alertBadges.tsx`,
   `keyboard/map-canvas-harness.tsx`. WS4a adds a sixteenth, `src/canvas/canvasMarks.ts` (type import only), which is
   version-bound by design: it alone knows Sigma's layer names.

PLACEHOLDER_REST
