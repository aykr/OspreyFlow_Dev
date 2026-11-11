# rules-b lane · report · T3b, the contrast probe's limits and Show as BPMN's task box (10 November 2026)

(T3's report is in git history, at ea3ba26 and before.)

1. **CARRIES row 110, Show as BPMN's task box: met.** The drawing's words now measure on their task box, `--text-primary` on `--surface-panel`, and pass, so the 12 listings came off. The task box filled in the words' own colour is red at 1.00:1 (Q7′).
2. **CARRIES row 121, the probe's limits: met.**
   - Points every 8px along the node's own words (Q1, red, with its control).
   - `inert` and pointer events lifted (Q4, with its control).
   - Outer shadows per node, by offset and spread (Q5); a descendant at the words (Q6).
   - Ink from SVG `fill` and `-webkit-text-fill-color`; the page is the browser's `Canvas` (V2).
   - The spread is counted before it is built (W2), gradientSurfaces gives its reason (V5), and the findings file is shape-checked (V4).
   - Still carried: the 5 × 3 grid for `bgOverlap`, a sixth line box, decision 3 under a cover, the root's spread, a modal `<dialog>`, and `clip-path` (RED_RECORD).
3. **merger-c2's three blockers: fixed.** The SVG under-path is a fail-closed allowlist laid at the shared ancestor (MP1 at 3.98:1, MP2, MP3; W1).
4. **Findings:** 78 looks and 140 findings in `a11y/contrastFindings.json`. Shell's menu-shadow listings came off with the true reach. Case's handle-over-label listings are new, all with their owners.
5. **Gates: ready-to-merge at d41df45** (tree e149207, rebased onto main affd759). `make -k ci` exit 0; `make test` pytest 10828 passed, 2 failed, vitest 3058 passed, 1 failed, all three environment (Valkey port, GPU, MatrixView timing); browser 975 + 34 passed in 14.1 min against 13.8. d9f1479 failed colour-drift and no-branches on my own text, fixed in d41df45 (`gates/d41df45.{test,ci,browser}.txt`). Not sent to merger-c2, which is closed this morning: the orchestrator's word.
6. **Friction row:** `process/friction/2026-11-10-rules-b-contrast-probe.md`. **Still running:** nothing.

## Decisions taken (each the recommended option; the owner may overrule)

1. **SVG shapes under a label's words.** Q: always a cover, as in T3, or a surface? **Chose:** a surface, through a fail-closed allowlist (merger-c2's suggestion), so Show as BPMN is measured rather than excused.
2. **The point cap.** Q: thin the sampling past it, or fail closed? **Chose:** fail closed past 600 points. No node on main reaches it.
3. **Decision 3's own reason under a cover.** Q: force a plant, or record that axe changes its reason? **Chose:** record it. The judgement has no branch on that reason beyond taking three rows, and a unit case holds it.
