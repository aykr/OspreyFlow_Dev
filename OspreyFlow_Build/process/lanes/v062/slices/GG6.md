# Slice GG6 · GG6 · Today's workspace moves to MapLibre 6 on Sigma 3: the MapLibre CVE closed

- **Build id:** GG6
- **Dial setting:** balanced
- **Rounds limit:** 2
- **After:** nothing on the line. **But `make trivy` cannot pass until the owner rules on the picomatch finding**
  (`BACKLOG.md`, "Found by the merge gate on AD2's first merge attempt": CVE-2026-112366, HIGH, no fixed version, dev
  tooling). That finding fails `make trivy` on main today, and this slice's acceptance runs `make trivy`. The slice may
  be built before that ruling, but it cannot pass its acceptance, or merge, until then.
- **Status of this brief:** the slice is the owner's (18 November 2026, build id GG6 on the plan, "under the standing
  approval"). The brief was written from the owner's words and the evidence of the same day.

## What

The owner's words, 18 November 2026: "today's workspace moves to maplibre-gl >=6.4.1 <7 on Sigma 3. Remove
@sigma/layer-maplibre and @sigma/edge-curve from apps/workspace/package.json. Remove the CVE-2026-85061 entry from
.trivyignore. Self-host the worker with setWorkerUrl. Apply ADR-014 Amendment 2 as accepted by me, not proposed."
And: "The evidence ran none of these in a browser, so treat every claim there as unproved until your test shows it. If a
browser run shows a regression, stop the slice and tell me. Do not fall back to 5.x: trivy still fails it."

Binding: `OspreyFlow_Build/spec/06_DECISIONS.md` ADR-014 (`:510`) and its Amendment 1 (`:543-570`); ADR-086 Amendment 1
(`:9745`), which made `apps/workspace/src/map/sigmaMaplibreLayer.ts` the product's own binding; `spec/02_GLASS_FRONTEND.md`
§5 (the performance budget).

**What exists** (read on main at e34d77f, 18 November 2026; nothing here was run in a browser):
- `apps/workspace/package.json:22` (`@sigma/edge-curve`) and `:24` (`@sigma/layer-maplibre`). No file imports either one.
  `src/canvas/GlassCanvas.tsx:16` mentions edge-curve only in a comment. `@sigma/layer-maplibre@3.0.0` has the peer
  range `maplibre-gl ^4.5.0`, and npm refuses 6.x beside it (`ERESOLVE`). `:37` `maplibre-gl ^4.7.1`.
- `src/map/MapView.tsx:30` `import maplibregl from "maplibre-gl"`. 6.x is ESM-only with no default export
  (6.0.0 release notes), so this becomes `import * as maplibregl`. A type-check of the whole of `apps/workspace/src`
  against 6.19.0 with that line changed gave 0 errors.
- The worker. 6.x finds `maplibre-gl-worker.mjs` beside `import.meta.url`. A Vite production build of the workspace on
  6.19.0 exited 0 but emitted no worker file, and pointed at `/assets/maplibre-gl-worker.mjs`. MapLibre's v5-to-v6
  migration guide says every bundler needs a one-time `setWorkerUrl()`. In Vite that is an import of
  `maplibre-gl/dist/maplibre-gl-worker.mjs?url`. The Vite dev server, which every Playwright suite here uses, was not
  checked.
- The attribution mitigation stays: `MapView.tsx:367` (`attributionControl: false`) and
  `keyboard/map-view.spec.ts:58-79`.
- 6.0.0 removed WebGL 1. Without WebGL 2, `new Map` throws `GPUInitializationError`. `MapView` has no handler.
- 6.19.0 depends on `zustand ^5.1.0`; the workspace has `^5.0.2` (5.0.15 installed). Read the lockfile diff.
- `.trivyignore:1-27` holds the CVE-2026-85061 entry.
- **No test today proves tiles load offline.** `keyboard/map-view-harness.tsx:70` uses "A raster provider whose tiles
  never arrive". The only proof that tiles render is `live/basemap.spec.ts`, which needs a live stack, and the live step
  is off.

## Acceptance test

Files:
- `apps/workspace/keyboard/map-tiles.spec.ts` (new).
- `apps/workspace/map-build/playwright.config.ts` (new): runs that same spec against a production bundle. Its
  `webServer` builds the harness page with `vite build` and serves it with `vite preview` on a `lanePort(...)` port of
  its own. Its `testDir` is `../keyboard` and its `testMatch` is `map-tiles.spec.ts`.

The spec drives the real `MapView` (extend `map-view-harness.tsx` or add a harness beside it) over a **synthetic vector
PMTiles fixture**, read through the real `pmtiles://` protocol path. The fixture holds synthetic shapes only, no map
data (rule 9). It is made by a script committed with it, and a test fails if the committed bytes differ from the
script's output. It asserts, under both the dev server and the production bundle:
1. the MapLibre version the page is running, read from the page, is `>= 6.4.1`;
2. the protocol read at least one **tile-block** range, not only the header and root directory (as
   `live/basemap.spec.ts` explains);
3. the canvas has map on it: more than one distinct colour where the fixture draws;
4. no request for the worker failed, and the page raised no error.

**Red today, for the right reason:** on main the page runs 4.7.1, so assertion 1 fails. The other three are expected to
pass on 4.7.1; they are there to catch a regression on 6.x. Shown red as well before the work counts (rule 15):
- the production run with the `setWorkerUrl` call removed (the worker 404s, so assertion 4 or 2 fails);
- `map-view.spec.ts`'s attribution case on 6.x with `attributionControl: true` planted;
- a new case in which, with WebGL 2 missing, `MapView` shows a message instead of a blank panel. Red with the handler
  removed.

The acceptance command also runs the performance gate (`npm run test:perf`), checks that `.trivyignore` no longer names
CVE-2026-85061, and runs `make trivy`. **If any browser run shows a regression on 6.x** (tiles, the camera across a
resize, the performance gate), stop and report: do not work round it, and never fall back to 5.x.

## Checks

From `OspreyFlow_Core`: `npx tsc -p .`; `npx vitest run src/map src/site`; the keyboard specs `map-view.spec.ts` and
`map-canvas.spec.ts`; and the Node half of the licence check (`node ../OspreyFlow_Build/tools/licence_check.mjs`), since
6.x brings new packages. All were green on main at e34d77f, before the slice.

## ADR-014 Amendment 2

Insert the text in `slices/GG6-ADR-014-amendment-2.md` into `OspreyFlow_Build/spec/06_DECISIONS.md` after `:570`, the end
of Amendment 1, before the `---` that precedes ADR-015. Its status is **accepted by the owner, 18 November 2026**. Before
merging, rewrite its "Not checked" paragraph to say what this slice proved in a browser and what it still did not.

## Start proof (standing approval, RULINGS.md 18 November, item 1)

Run on main at e34d77f in a scratch worktree, with the exact frozen commands (`OSPREY_PORTS_SLOT` 19 for the proof):

| Command | Result on main | Reading |
|---|---|---|
| checks | **green**: tsc 0 errors; licence check passed; vitest `src/map src/site` passed; keyboard `map-view.spec.ts` 10/10 and `map-canvas.spec.ts` 3/3 | as required |
| acceptance | **red** at its first step: `map-tiles.spec.ts` does not exist on main | The slice's own new file cannot exist on main (the ruling's reading). The red for the right reason (the page runs 4.7.1) is the builder's first commit to show. |
| acceptance, later parts run alone | `npm run test:perf` **green** (4/4); `! grep -q CVE-2026-85061 .trivyignore` **red** (the entry is there, the right reason); `make trivy` **red** on picomatch CVE-2026-112366 only | `make trivy` is red on main for a reason outside this slice (see **After**) |

Citation check: every file and line cited above was read on main at e34d77f.

## Out of scope

- Sigma 4, in either tree. The owner's rulings of 18 November (`RULINGS.md`) put Sigma 4 into the GOV.UK modules first;
  today's workspace stays on Sigma 3.
- Rotation and pitch (a backlog row).
- `@sigma/layer-maplibre` 4.x.
- Any change to the CSP: the workspace has none today.
- The picomatch finding: its `.trivyignore` entry is the owner's to give, not this slice's.
- Any change to `OspreyFlow_Core/Makefile` or the CI workflow file.

Stop and ask rather than answer:
- a browser regression on 6.x;
- a licence the checker refuses among 6.x's new dependencies;
- zustand moving in a way that changes the working set's own tests.
