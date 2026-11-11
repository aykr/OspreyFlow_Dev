# rules-b lane · report · T3b, the contrast probe's limits, and its server round (10–11 November 2026)

(T3's report is in git history, at ea3ba26 and before. T3b's first gating, at d41df45, is at 8eb8c95.)

1. **CARRIES rows 110 and 121: met at d41df45**, as reported there. Show as BPMN's task box is measured, and the probe's limits closed (`t3b/RED_RECORD.md`).
2. **Sent back, 11 November:** the merger's server runs were red (8 failed on T3b's own tree), with the probe's own "not measurable" findings.
   - The UI font falls back to `system-ui`, so on Linux the words move a few pixels. Three of the probe's decisions turned on that: a shadow's reach, which point first met an open menu, and whether the probe scrolled at all.
3. **The fix, at be4052a:**
   - a shadow is measured by what Chromium paints at each point (a Gaussian of half the blur plus a margin read band by band from Chromium's pixels), laid at every place in the words' chain, never failed by its reach;
   - a point hidden under an opaque cover the hit test finds over the words, or clipped by a scrolling ancestor, is not judged, and words hidden at every point are unmeasurable;
   - every node is scrolled into place at once, and every scroll restored after it.
4. **Red, at the real call site:** unit cases 36, with S1 to S10, H1 and H2 red. Browser plants and controls ran on the server in slot 13:
   - the orchestrator's three silent-pass plants are red;
   - each new branch has a control with that branch removed;
   - the lane-reviewer's three passes are answered (`t3b/RED_RECORD.md`; the logs are in `t3b/server-round-plants.txt`).
5. **Findings:** Places' GOV.UK "Case: Kestrel" came off: it is measured now, 17.15:1, in 5 runs of 5. Its two other menu listings give the strict reason "hidden at every point". Nothing new was listed.
6. **Gates at be4052a** (rebased onto main a7bb34a; the wip commit dropped; HANDOFF.md in no commit): every run below is on the test server.
   - **Browser set, slot 13, 20261111T135522Z:** 976 + 32 passed. All 5 failures were timeouts while the merger's and docs' runs loaded the server (load average 24 to 37): the network canvas never drawn (2), GOV.UK's `data-brand` (1), two harness screens (2). On the retakes, all 5 passed, then both canvas files whole (13). No contrast finding failed. The earlier full runs on this round's code, at 9c6b9dc, 8bd3eef and 896bbf7, are in `t3b/RED_RECORD.md`.
   - **`make -k ci`, 20261111T141931Z:** exit 2, on `trivy-image-workspace` alone: libxslt 1.1.43-r3 in the image. That is the server's stale layer cache (MORNING item 36; v0.5.0's image has r4), not this branch, which touches no image.
   - **`make test`:** not re-run. The branch changes only the workspace's a11y probe, its judgement and their unit cases (vitest src/color: 112 passed). `gates/be4052a.{browser,ci}.txt`.
7. **Friction row:** `process/friction/2026-11-10-rules-b-contrast-probe.md`, the server round. **Still running:** nothing.

## Decisions taken (each the recommended option; the owner may overrule)

1. **SVG shapes under a label's words.** Q: always a cover, as in T3, or a surface? **Chose:** a surface, through a fail-closed allowlist (merger-c2's suggestion), so Show as BPMN is measured rather than excused.
2. **The point cap.** Q: thin the sampling past it, or fail closed? **Chose:** fail closed past 600 points. No node on main reaches it.
3. **Decision 3's own reason under a cover.** Q: force a plant, or record that axe changes its reason? **Chose:** record it. The judgement has no branch on that reason beyond taking three rows, and a unit case holds it.
4. **A shadow's placement.** Q: none, under or over the words only, or every place in the words' chain? **Chose:** every place, deduplicated where a layer paints nothing. A random search found a case where only "between the layers" is the worst.
5. **Words hidden at every point.** Q: pass (nothing is shown), or unmeasurable? **Chose:** unmeasurable, the orchestrator's condition, because a probe that excluded every point has measured nothing.
6. **σ.** Q: the spec's blur / 2, a remembered Skia figure, or a measurement? **Chose:** measured from Chromium's pixels. Blur / 2 plus a margin that bounds the measured shortfall band by band.
