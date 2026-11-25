# Slice GG2a · GG2 · The budget page: Sigma 4 in the page service, measured against spec/02 §5 at 50,000 nodes and 250,000 links, before any graph module is built (DRAFT for the owner's rulings at about 12:30, 25 November 2026; no row)

**Status: a draft.** No row and not started until the owner rules. An away round on the server's build account
**only if PL7f has merged by 13:00** (the owner's plan for 25 November); its own branch, a commit at least every 15
minutes, nothing merged or pushed to the dev repository. **The budget itself is measured on the owner's Mac when he
is back** (his ruling of 18 November, `RULINGS.md` line 386: "GG2's scope and the I12 thresholds [deferred] until
GG2a (the budget page) has measured Sigma 4 on the owner's Mac; the numbers go to the owner then").

## What exists today (a read-only scout, 25 November 2026)

- **The rulings (18 November, `RULINGS.md` about lines 110 to 124):** "The GOV.UK graph and map modules (R4, R8; GG2
  and GG5 on the plan) start on Sigma 4. R4's first step proves the performance budget (`spec/02` §5) on Sigma 4, and
  falls back to Sigma 3 if it cannot. **The shared package imports no `sigma`, `@sigma/*` or `maplibre-gl`**";
  "Moving today's React workspace to Sigma 4 is decided after R4 has met the budget."
- **The budget (`spec/02_GLASS_FRONTEND.md` about lines 2232 to 2265):** first interactive frame under 2.5 s, pan and
  zoom at 60 fps, an expansion of up to 500 nodes under 800 ms, "on a 2021-class laptop, integrated graphics, against
  a 50k-node / 250k-edge working set"; "**The `pages` modules meet the same budget (ADR-152 I12)** ... by
  `apps/pages/test/perf/`. Sigma 4 has no `canvas.sigma-nodes`, so its readiness signal is its own, shown red on a
  selector that never matches before any figure from it is believed (rule 15)."
- **ADR-152 I12** (`spec/06` about line 41234): "`apps/pages/test/perf/graph.spec.ts` at 50k/250k, the thresholds of
  `spec/02` §5 unchanged, with a Sigma 4 readiness signal"; its red is "a readiness selector that never matches".
  **I13** (about line 41235): `glass-shared` imports no `sigma`, `@sigma/*` or `maplibre-gl`
  (`scripts/version_isolation_check.mjs`).
- **The workspace's CI gate today** (`apps/workspace/perf/perf.spec.ts`): the 50,000 / 250,000 fixture
  (`perf/fixture.ts`), a first frame under 30,000 ms ("deliberately much looser" than §5 under CI's software
  rendering) and a sweep near 730 ms per frame under SwiftShader. **The owner's Mac, Sigma 3** (`PL4_BASELINE.json`
  line 152): first frame 7,155 to 8,047 ms, sweep 1,588 to 1,885 ms per frame.
- **The earlier Sigma 4 attempt (parked 20 October, `process/HANDOVER_2026-10-20.md` about lines 27 to 44; ADR-118 on
  its branch only):** in CI the React workspace on Sigma 4 took a first frame of 27.0 s (gate 30) and a sweep of
  **9,357 ms per frame (gate 3,000)**; locally 10.9 to 12.4 s first frame against main's 5.8 s. That was the React
  workspace, not a page-service module; it is the risk this slice measures first.
- **Not anywhere today:** Sigma 4 (every package pins `sigma` and `@sigma/*` at `^3.0.0`); `apps/pages/test/perf/`;
  any graph route in the page service. `apps/pages/scripts/assets.mjs` lines 31 to 33 refuse every drawing import
  (`ALLOWED_DRAWING = []`, `DRAWING = /^(sigma|@sigma\/.+|maplibre-gl)(\/|$)/`). **The licence register
  (`spec/LICENCE_REGISTER.yaml`) has no row for `sigma`, `graphology` or `maplibre-gl` at all**, though the workspace
  ships them: a gap of its own, for the owner (`make licence-check` reads the lock, not the register, it seems).

## Questions for the owner (my proposal first in each)

1. **What the page is.** (a) **A module of its own under `apps/pages/modules/graph/`** (ADR-152: interactive modules
   are kept once for both trees) that draws the perf fixture with Sigma 4, served only by the perf harness, **in
   neither tree's route list and never in a production render**; (b) a routed page in the GOV.UK tree behind the
   pages setting.
2. **The CI gate.** (a) **The workspace's CI gate, unchanged** (first frame under 30,000 ms, the sweep's gate as
   `perf.spec.ts` holds it) in `apps/pages/test/perf/graph.spec.ts`, red first on a never-matching readiness
   selector, plus a recorded three-run figure like `PL4_BASELINE.json`; **§5's own numbers (2.5 s, 60 fps, 800 ms)
   are measured on your Mac when you are back and brought to you**, as your 18 November ruling says; (b) §5's numbers
   as the CI gate now.
3. **The fixture.** (a) **The workspace's own generator** (`apps/workspace/perf/fixture.ts`), moved to
   `packages/glass-shared` (plain TypeScript, no drawing import) so both measure the same graph; (b) a copy (not
   proposed: two fixtures drift).
4. **The version.** (a) **The newest Sigma 4.x release at least 14 days old, pinned exactly**, with the graphology
   version it needs; `ALLOWED_DRAWING` gains `sigma` (and only what the module imports) for that module's bundle
   alone; the licence register gains rows for Sigma (MIT) and graphology; (b) your choice of version.
5. **If the budget is missed in CI:** (a) **the slice stops and the figures come to you** (your ruling: fall back to
   Sigma 3), never a loosened gate; (b) carry on to your Mac's measurement anyway.
6. **The licence register's missing rows** for what the workspace ships today (`sigma` 3, `@sigma/*`, `graphology`,
   `maplibre-gl`): (a) **a separate small part**, not GG2a; (b) in GG2a.

## The table of cases (each red first, planted faults at the real call site: rule 15)

| # | Case | Expected |
| --- | --- | --- |
| 1 | The readiness signal | `graph.spec.ts` waits on the module's own ready signal; with a selector that never matches it is red (never ready), shown before any figure is believed |
| 2 | First frame at 50,000 / 250,000 | under the CI gate of question 2, three runs recorded |
| 3 | The pan and zoom sweep | the average frame time under the sweep's gate, three runs recorded |
| 4 | An expansion of up to 500 nodes | timed and recorded (gate as question 2 decides) |
| 5 | The shared package | `version_isolation_check.mjs` red with a planted `import "sigma"` in `glass-shared`, green without (I13) |
| 6 | The page service's bundles | `sigma` allowed in the module's bundle alone; a planted Sigma import in any other page is refused (`bundleRules.test.ts`) |
| 7 | No React | `no_react_check.mjs` green with the module in |
| 8 | Not served in production | no tree's route list names it; a render of every profile has no path to it (if question 1 is (a)) |
| 9 | The licence | the register's rows for Sigma 4 and graphology; `make licence-check` green, and red with the row removed |

## Checks (to be frozen at the start)

The pages workspace tests, lint, typecheck, `no_react_check.mjs`, `version_isolation_check.mjs`, the new perf spec
(run by its own target), `test_no_react_check.py`, `test_pages_foundation.py`, `test_pages_setting.py`,
`licence-check`, `design_check`. The perf figures are recorded with the machine they were taken on; a figure taken
without the stack lease, or on another account's run, is not a measurement (rule 14).

## Out of scope

The graph module itself (a list of cases, the working set, its capped refusal: R4's later slices); the React
workspace's move to Sigma 4 (WS4, after the budget is met); any other drawing library.
