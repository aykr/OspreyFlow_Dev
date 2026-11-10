# rules-b lane · report · T3, dialogs' colour contrast actually gated (10 November 2026)

(L2.11a's report is in git history, at 35ed3df and before.)

1. **The gate fails on axe's undecided colour contrast: met.**
   - `a11y/undecidedContrast.ts` reads each node axe leaves incomplete. `src/color/textContrast.ts` judges it in Node, failing closed on anything it cannot read or model.
   - It is called after every axe scan: every-harness, the workspace's `a11y.spec.ts` and `canvas-focus.spec.ts`, and the install harness's two specs.
2. **Red on both plants: met.**
   - P1, the L2.11a dialog text on its own surface: 6 of 6 looks.
   - P2, platform-b's 1:1 panel words: 3 of 3.
   - Then the stale check, the oklab grid, a foreign `pointer-events: none` overlay, a `none` colour, and each sibling; all of them are in `t3/RED_RECORD.md`.
   - Unit cases are in `textContrast.test.ts`, with each rule's planted fault red (U1 to U19).
3. **Green with each finding listed: met.** Main's findings are listed in `CONTRAST_FINDINGS` (every-harness) and `SHOWCASE_CONTRAST_FINDINGS` (`a11y.spec.ts`).
   - Each is excused only by its selector, its text and its ratio. An unmeasurable one is excused by its exact reason, pinned to its own surfaces' ratio.
   - A listed finding no longer found fails, and so does a listed title that is not a look.
4. **Findings by owner:**
   - platform: the map chip;
   - design system: the toast glyph;
   - home: the key cap;
   - shell: variant b's ⋯ and places' open menu;
   - case: the boards' lines and views' delete question;
   - rules: the metrics rarity note;
   - plus the truncated texts this round lists (RED_RECORD).
5. **Reviews:**
   - Mine and the orchestrator's of 9dab1ef: 10 must-fixes, all fixed in 7ce19d0.
   - merger-c2's of bd9b4ef: 2 must-fixes, fixed in 46e53d3.
   - merger-c2's of e94b18c: 3 more silent passes, fixed this round.
6. **Gates:** GATES.
7. **Friction row:** `process/friction/2026-11-10-rules-b-contrast-gate.md`. **Still running:** nothing.

## Decisions taken (each the recommended option; the owner may overrule)

1. **Where the judgement lives.** Q: in the page (`page.evaluate`) or in Node? **Chose:** Node (`src/color/textContrast.ts`), so tsc and Vitest cover every rule. The orchestrator ratified it.
2. **The sibling scans.** Q: a patch, or the branch? **Chose:** the branch. The orchestrator ratified it.
3. **axe's "partly obscured".** Q: always fail it closed and list, or measure it? **Chose:** measure it, when the probe finds nothing foreign at its points. The probe scrolls the text into view and lifts every element's pointer events, and surfaces are judged point by point.
   - Always closed (merger-c2's suggestion, tried in the browser) failed 174 looks. Nearly every one was text below the fold or past a scrolling box. Listing them would have excused text wholesale.
   - The old clip exception's faults are gone either way. Its wrong surface for spilling text is now judged per point (merger-c2's plant measures 1.26:1), and there is no clip-or-cover classification left to prove.
4. **axe's `bgOverlap`, `imgNode`, `bgImage`.** Q: always closed, or measured when the probe finds nothing? **Chose:** as decision 3, measured only when the probe finds nothing foreign at any point. The probe lifts every element's pointer events, and its points spread first, middle and last. A dialog's own text, which axe often marks this way, is then decided rather than excused wholesale.
5. **The arithmetic duplicated** (`src/map/contrast.ts`, `src/color/oklab.ts`). Q: reuse them by changing glass's files, or keep a local copy? **Chose:** the local copy. merger-c2 carries the reuse to glass.
6. **The SVG link layer on boards.** Q: paints wherever its box is, or only through its shapes? **Chose:** only through its shapes, so a handle is unmeasurable only where an edge runs under it.
