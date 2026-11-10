# rules-b lane · report · T3, dialogs' colour contrast actually gated (10 November 2026)

(L2.11a's report is in git history, at 35ed3df and before.)

1. **The gate fails on axe's undecided colour contrast: met.** `a11y/undecidedContrast.ts` reads what axe leaves incomplete, and `src/color/textContrast.ts` judges it in Node, failing closed. It runs after every axe scan: every-harness, `a11y.spec.ts`, `canvas-focus.spec.ts`, and the harness's two specs.
2. **Red on both plants: met.** The L2.11a dialog plant, 6 of 6; platform-b's 1:1 panel words, 3 of 3. Then the stale check, the oklab grid, a foreign overlay, a `none` colour, merger-c2's spill and sized gradient, a mistyped title and each sibling. Unit faults U1 to U19 are red too (`t3/RED_RECORD.md`).
3. **Green with each finding listed: met.** `a11y/contrastFindings.json` holds 84 looks and 132 findings. Each is pinned to its text, and to its ratio or exact reason plus its own surfaces' ratio. A stale listing fails, and so does a title that is not a look.
4. **Findings by owner:**
   - platform: the map chip; shell: variant b's ⋯ and places' menu; case: the boards' handles;
   - rules-b: Show as BPMN's task box; home: the key cap (fixed on rules-hyg); design system: the toast glyph.
   - For T3b: a pressed button's `:active`, a cover between probed points, and merger-c2's carries.
5. **Reviews:** mine and the orchestrator's (9dab1ef), then merger-c2's three. Every must-fix is fixed; decision 3 departs from one suggestion, and merger-c2 accepted it.
6. **Gates at c66b1e0** (on main ba14a00):
   - `ci`: green.
   - `test`: 10680 + 3030 passed; 4 environment failures, explained.
   - `browser`: 967 + 34 passed.
7. **Friction row:** `process/friction/2026-11-10-rules-b-contrast-gate.md`. **Commits:** `main..` on lane/rules-b. **Still running:** nothing.

## Decisions taken (each the recommended option; the owner may overrule)

1. **Where the judgement lives.** Q: in the page (`page.evaluate`) or in Node? **Chose:** Node (`src/color/textContrast.ts`), so tsc and Vitest cover every rule. The orchestrator ratified it.
2. **The sibling scans.** Q: a patch, or the branch? **Chose:** the branch. The orchestrator ratified it.
3. **axe's "partly obscured".** Q: always fail it closed and list, or measure it? **Chose:** measure it, when the probe finds nothing foreign at its points. The probe scrolls the text into view and lifts every element's pointer events, and surfaces are judged point by point.
   - Always closed (merger-c2's suggestion, tried in the browser) failed 174 looks. Nearly every one was text below the fold or past a scrolling box. Listing them would have excused text wholesale.
   - The old clip exception's faults are gone either way. Its wrong surface for spilling text is now judged per point (merger-c2's plant measures 1.26:1), and there is no clip-or-cover classification left to prove.
4. **axe's `bgOverlap`, `imgNode`, `bgImage`.** Q: always closed, or measured when the probe finds nothing? **Chose:** as decision 3, measured only when the probe finds nothing foreign at any point. The probe lifts every element's pointer events, and its points spread first, middle and last. A dialog's own text, which axe often marks this way, is then decided rather than excused wholesale.
5. **The arithmetic duplicated** (`src/map/contrast.ts`, `src/color/oklab.ts`). Q: reuse them by changing glass's files, or keep a local copy? **Chose:** the local copy. merger-c2 carries the reuse to glass.
6. **The SVG link layer on boards.** Q: paints wherever its box is, or only through its shapes? **Chose:** only through its shapes, so a handle is unmeasurable only where an edge runs under it.
