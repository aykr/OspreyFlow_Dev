# Glass lane · brief L2.3, part 1 · the case screen's lightening: a prototype round for the owner

Written by the orchestrator, 7 November 2026, after L2.2's merge (`fd38da4`), on the owner's word ("Glass
builds options now"). Opus, medium. Size S. **No product code in this part.**

**Binds.** `process/CLAUDE.md` rules 1–15; ADR-145 decision 4 (the right-hand column opens with the
Inspector only; Metrics and the Query builder one click away, keeping their order and folding, ADR-085,
ADR-096; the analysis canvas read-only for drawing, ADR-143 C6; further cuts are prototype rounds, N4);
`spec/02_GLASS_FRONTEND.md` (the case screen, the panels); the navigation prototype,
`spec/glass_redesign/navigation_prototype.dc.html`.

**Do.** Build two or three clickable variants of the case screen's right-hand column and top controls in
a keyboard harness (`keyboard/case-screen-options-harness.*`, never wired into the app), each in the dark,
light and GOV.UK themes. One variant is ADR-145 decision 4 exactly as written. The others are the
smallest changes beyond it that cut the most controls before the canvas. The ADR counts about 25
controls, and three panels holding 15 parts. For each variant give:
- a screenshot in all three themes;
- the count of controls before the canvas;
- what moves where, and what becomes one click further away;
- a one-line trade-off.

Then write the choice as a multiple-choice question, at most four options with your recommendation
first, and **send it to the orchestrator** (the session named `ospreyflow-7e`). Don't ask in your own
window.

**Files.** The new harness, its screenshots under `process/lanes/glass/l2.3/`, and your friction
fragment. No `src/**` change.

**Report** (Prompt L's format, at most twenty lines, in `REPORT.md`): the variants, the question and its
options, and where the screenshots are. Then wait for the owner's choice, which comes as part 2's brief.
