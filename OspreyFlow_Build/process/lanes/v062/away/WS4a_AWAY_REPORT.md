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

## The table of cases (the draft's, each red first; planted faults at the real call site, rule 15)

Records: `WS4a_records/` beside this report (the plant scripts, their logs, the run logs). "Share" is the share of the
scene's 540,000 pixels unlike the reference by more than the channel step (16).

| # | Case | State | Evidence |
| --- | --- | --- | --- |
| 1 | Each scene against its reference, on Sigma 3 | **built, red then green** | green: 0 pixels differ at all, every scene, six runs (`compare-sigma3-self.log`, and three earlier runs before the communities scene). Red: the dotted program swapped for `EdgeLineProgram` at `GlassCanvas.tsx`'s program table: links 0.31%, links-zoomed-out 0.09%, and the four scenes on the chain (it has a dotted link) 0.05%; nodes, labels and communities stay green. Also the dashed program swapped (an inferred link drawn solid): links 0.13%, zoomed out 0.012%, the rest green. The draft expected "red on the dotted scene only": the scenes are grouped differently (one scene holds every link kind), so it is red wherever a dotted link is drawn and nowhere else |
| 2 | A label style change | **red** | `labelStyle.ts`'s `fontFor` one pixel larger: labels 0.39%, and every scene with labels |
| 2b | The export's watermark (added) | **red, after a fix** | first planted with the comparison as written: **green, 0 pixels**, because the exported PNG is drawn on a transparent ground and its black-at-75% watermark changes opacity alone. The comparison now reads opacity (`44b096baa`); the arithmetic's own case is red without it (`plant_alpha.log`); the plant is red with the words replaced (export 894 pixels, 0.17%). **With only the separator changed (` · ` to ` - `) it is green: 5 pixels, under the tolerance's 54.** That is a true limit of the tolerance as set (question 6); the watermark's words are better held by a unit test of `chartWatermarkText` than by pixels |
| 3 | Community links zoomed out (ADR-119) | **red** | scene `communities`: 8 × 60 nodes, 14,196 links, the canvas's own seeded Louvain. `drawsCommunityLinks` (glass-shared, the real switch) planted `false`: SEE_PLANT_3 |
| 4 | The map layer | **red** | scene `map`: the Map view on GG6's synthetic PMTiles archive (`map-tiles-harness.tsx`, served ranged and with its bearer token as `map-tiles.spec.ts` serves it), the Sigma layer bound over it by `sigmaMaplibreLayer.ts`. The camera sync offset one pixel at `syncMapWithSigma` (`fitBounds(…, { duration: 0, offset: [1, 0] })`): map 399 of 700,000 pixels (0.057%), red; every other scene green. **Limit:** that harness loads no product face, so the map's node labels are in the system's fallback face: stable on one machine, not covered by the renderer check |
| 5 | The tolerance | **red** | set from three runs (0 pixels differ at all in any scene: `TOLERANCE.json` records the set-from); share 0.0001 (54 pixels) at channel 16, below the smallest planted signal (63 pixels). The ceiling, `CEILING` in `canvasCompare.ts`, is share 0.0005, channel 32: below every plant's own scene. A tolerance of 100% planted in `TOLERANCE.json`: the ceiling case and every scene red; `canvasCompare.test.ts` has its own reds without a browser |
| 6 | The reference-making command | **red** | `npm run canvas-compare:references -- --reason "…"` (`keyboard/canvas-compare/make-references.mjs`): refused with no reason, in CI, or with the canvas's own files uncommitted; records who, why, the commit, the machine and the WebGL renderer in `REFERENCES.json`. A reference replaced by hand (links.png overwritten): "every reference is the one the command recorded" red, and the scene red. The spec never writes a missing reference (unlike `toHaveScreenshot`), and on another WebGL renderer it fails in words rather than comparing |
| 7 | I20, the same versions | **red then green** | green on main and with `--release`. Red: `apps/pages` pinning `maplibre-gl` 6.5.0 (I20's own red in ADR-152's table) and GG2a's Sigma 4.0.6, each naming the package and both versions; and on GG2a's real lockfile |
| 8 | I20, a listed window | **red** | listed with its day: green. No day, a day that is not one (`2026-11-31`, `26 November 2026`, `2026-1-5`, `soon`), versions other than the tree's, an entry whose difference has closed, an entry for a library I20 does not hold, a file of any other shape: each refused |
| 9 | I20, at release | **red** | `--release` refuses while the file lists anything; the release paths' wiring is the owner's diff (`I20_RELEASE_LOCAL.diff`, `I20_PUBLISH.diff`) |
| 10 | I20, a nested duplicate | **red** | `node_modules/@sigma/node-border/node_modules/sigma` at another version (the workspace reaches two); a second graphology under the linked shared package; `pages` on Sigma 4 with a Sigma plugin hoisted to the root (its peer resolves to Sigma 3): **not excusable by the window** |
| 11 | The budget gate's readiness | **red then green** | the harness switched to the canvas's mark before the canvas set it: `TimeoutError: page.waitForFunction: Timeout 60000ms exceeded` (`perf-red-unmarked.log`). Then green; figures below |
| 12 | No `.sigma-*` name in any spec | **red then green** | `test_no_sigma_class_names_in_the_workspace.py`, over the whole workspace, red on the tree as it was (all six places found, `sigma_class_red.log`), and on its own comments once (they named the old class; reworded) |
| 13 | Nothing visible changed | SEE_SUITE |

SECTION_FIGURES

## Questions that are the owner's (not guessed)

1. **The version window entry when GG2a merges.** GG2a's lockfile fails I20 with the window empty. Proposal: (a) the
   entry is written in GG2a's merge (it opens the window; ADR-002 Amendment 1 item 3, "written ... with the day it
   opened"), and WS4b removes it in the merge that ports the workspace (the check refuses an entry whose difference has
   closed, so WS4b cannot forget). (b) WS4a, if it merges second, writes it. Either way the release is frozen from that
   day until WS4b, which decision 9 already says.
2. **Where the comparison's references are made, and when it joins CI.** D268 answered draft question 4 with (a): made
   in CI's own browser image. This round could not run CI (no push), so the references are made here, with SwiftShader,
   and the spec refuses to compare on another WebGL renderer. Proposal: (a) the owner runs `npm run test:canvas-compare
   --workspace apps/workspace` once on a CI runner (a branch push or `workflow_dispatch`). If it is green, apply
   `COMPARE_CI.diff` and `COMPARE_CORE_MAKEFILE.diff` as they are. If it differs, remake the references on the runner
   with the command (`--reason "made on CI's runner"`) and commit them, then apply the diffs. (b) Make CI's set first,
   whatever the result. The Mac makes its own set only if the owner wants a local check.
3. **What the budget's readiness should mean on Sigma 4** (GG2a's question 2, the same question from this side). WS4a
   kept `readyAt` meaning what it measured on Sigma 3, the renderer mounted (`data-canvas-state="mounted"`), so the
   figure did not move. The canvas also marks `"drawn"` after its first finished frame, ready for a gate that wants the
   frame itself. Proposal: (a) keep "mounted" for WS4b, so Sigma 3 and Sigma 4 are compared like for like, and decide
   GG2a's question 2 for both front ends at once. (b) Move both to "drawn" now.
4. **`release_local.py` and `publish_user_repo_update.sh` as release gates.** Proposal: (a) apply `I20_RELEASE_LOCAL.diff`
   and `I20_PUBLISH.diff` (written as diffs because they are release gates, though `release_local.py` is not on the
   protected list). The release-local diff has no test of its own; `test_release_owed.py`'s pattern would take one case
   (a window entry planted, the release refused before anything is built). (b) The release workflow instead.
5. **I20's third test, `tests/glass_trees/test_no_sigma_page_merges_in_the_window.py`** (ADR-152's table: no route in
   either tree mounts a Sigma module except R4's budget page while the window lists anything). It is part of I20 but was
   not in WS4a's table of cases, and it needs GG2a's page to have anything to check. Not built. Proposal: GG2a's merge or
   WS4b, whichever touches `apps/pages` routes next.

SECTION_TAIL
