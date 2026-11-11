# rules-b · T3b · the orchestrator's review of 9697ad3: the fixes, item by item (11 November 2026)

Written at the pause for the move to sol; HANDOFF.md points here.

## The orchestrator's must-fixes (its message after "ready-to-merge 9697ad3")
1. **hides()'s guards, each shown red with that guard removed: DONE, d677105** (RED_RECORD's review-fixes section).
   - The earlier see-through plants sat on "If a Person meets" made 1:1, so they failed with or without a guard.
   - Re-plant on the words' own 13:1, under a see-through cover over half of them, and for each guard in turn show that removing it makes the words pass silently:
     - the opacity walk in `opaque()` (the cover's own opacity, and an ancestor wrapper's);
     - `backgroundClip !== "border-box"` (a content-box clip);
     - the filter, blend, mask and clip-path walks, each on the cover and on an ancestor;
     - the mask-border check, and the SVG exclusion (item 2);
     - the 1px slack, the clip check's narrowing (overflow and the containing-block walk), and the corner test.
   - Expect some to be unreachable, and record why rather than claim a red: Chrome's hit test already respects `clip-path` and `border-radius`; removing the 1px slack only adds covers; the clip narrowing is backed by "hidden at every point".
   - **Commit the plant files so they can be re-run from the tree.** Plan: `a11y/plants/*.plant.ts`, with their own Playwright config whose `testMatch` is `*.plant.ts`, so CI's a11y runs never pick them up. A runner writes the branch-removed variants from `undecidedContrast.ts`, runs them, and deletes them, so `eslint .` never sees them.
   - The scratch plant and variant files from this session are in `/private/tmp/claude-502/-Users-ayankar-dev-osprey-wt-rules-b/8a0a5caa-29c4-4b49-aac6-0502332354a3/scratchpad/plants` (gone once this machine's /tmp is cleared; the plant shapes are also in `t3b/server-round-plants.txt`'s headings).
2. **SVG elements trusted as opaque by their CSS background, and the mask border: DONE, 7befa52, planted red in d677105.**
   - `opaque()` refuses any SVG element but the root, which covers `hides()` and the walk up the words' own tree.
   - `hides()` refuses a cover under `mask-border-source`, `-webkit-mask-box-image(-source)`.
   - Owed: plants, both red. First, `<rect style="background-color:#fff" fill="rgba(255,255,255,.8)">` over half a Show as BPMN label: about 1.5:1 there, and before 7befa52 the label passed on its uncovered half. Second, a mask-border cover.
3. **"Hidden at every point" listings excuse unconditionally: DONE, 664ea74.**
   - `onOwnSurfaces` returns null when every point is hidden, so `ownRatio` is null, and `excuses()` with `own: null` always holds.
   - Fix: on that path, compute `ownRatio` over all points with `hidden` ignored. Give the two places GOV.UK listings (`.context-banner__sep…:nth-child(4)` "·" and `span:nth-child(5)` "reads Prison intel") real pins, which were 19.59 on main.
   - Owed: a unit case red with the pin dropped.
4. **REPORT.md item 6 misstates the retakes: DONE, in the rewritten REPORT.** The two canvas tests failed the first retake too (20261111T141740Z) and passed only on the second (20261111T142957Z, load average 37). State it as it happened.

## Minors
- **σ, one geometry only; rounded corners "can only overstate" is not conservative: DONE, 110c368, measured in 8 geometries.**
  - The finding: contrast against a shadow's alpha is monotone until the background's luminance crosses the ink's, so overstating alpha can jump past a 1:1 crossing.
  - My answer is in `t3b/wip-alpha-bracket.patch` (against `src/color/textContrast.ts` at 9697ad3/7befa52):
    - each shadow's alpha is bracketed between a least and a most;
    - every placement is measured at both ends;
    - if the words and what lies under them swap lightness across the bracket, the worst is 1:1;
    - near a rounded corner the least is 0.
  - It names `SHORT_MEASURED`, which is **not yet measured**. Measure on the server the most Chromium paints *under* the Gaussian, as min(measured − Gaussian) per band of σ, with the band spec as in `server-round-plants.txt`'s last section. Also measure an offset and a rounded geometry, not only a straight edge with spread equal to blur. Then apply the patch, fill the constant from the figures, write unit cases (a crossing case red), and show them red.
- **Friction:** the server-round fragment becomes one row, with current figures (36 cases, S1 to S10, plus what comes).
- **RED_RECORD.md line 3** ("All browser runs were local") is stale: say the first rounds were local and the server round ran on the server, slot 13.
- **GOV.UK `data-brand` 5s wait:** it failed in every full run (4, 1, 4, 1). It becomes a CARRIES row, not a retake each time. CARRIES is written at the merge, so put the row's words in REPORT for the orchestrator.

## Then
Run the browser set once on the server, in slot 13 (`stack_lease.sh offline rules-b`, `OSPREY_PORTS_SLOT=13`, the
command in `gates/be4052a.browser.txt`'s first line). Then `make -k ci` through offline, and "ready-to-merge" to the
orchestrator by message. The merger is closed; the orchestrator reviews and merges.

**Must not redo:** the rebase (done; main moved later, but a gated lane does not rebase again unless asked). The
server round's earlier plants and records stay as they are.
