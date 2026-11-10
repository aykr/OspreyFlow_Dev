# rules-b · T3b · red record: the contrast probe's limits, and Show as BPMN's task box (10 November 2026)

All browser runs were local, in the orchestrator's slot (`OSPREY_PORTS_SLOT=9`), against 9dd994b as committed. Every plant was restored after its run.

## Red in Node (`src/color/textContrast.test.ts`, 26 cases; each fault planted in `textContrast.ts`, then restored)
- **V1:** an SVG label's shapes ignored. Red: the label measured on its task box.
- **V2:** the page assumed white. Red: the dark-canvas case.
- **V3:** the spread counted only after it is built. Red: the cap case.
- **V4:** an unmeasurable entry's fields not checked. Red: the findings-file case.
- **V5:** a picture reported as an unread gradient. Red: 1.

## Red in the browser, at the real call site (Show as BPMN's dialog, `rule-standards-harness open=1`, and Home)
- **Q1, merger-c2's narrow overlay** (an `rgba(0,0,0,.6)` strip at x 60–140 over the dialog): 3 of 3 red, the dialog's words "over or under div".
  - Control: points only at each box's ends (the old sparse sampling). "Business-rule task:" and the long explanation then pass, while the 8px points catch them. The branch is proven node by node.
- **Q4, an `inert` overlay over the dialog:** 3 of 3 red.
  - Control: with `inert` not lifted for the probe, 3 of 3 pass.
- **Q5, an outer shadow** (`0 0 0 2000px rgba(0,0,0,.6)` from a 1px box): 3 of 3 red, "over or under the shadow of div".
- **Q6, a descendant's background under the title's own words:** 3 of 3 red, "over or under span".
- **Q7, the drawing's words in the task box's own fill:** 3 of 3 red, "End" at 1.00:1 (1.08:1 in one theme). It is measured on the box, not unmeasurable.
- **Q3, a cover over Home's case name below the fold:** 3 of 3 red, "over or under span".
  - Two first shapes changed the page itself, an absolute sibling and a relative shift. axe then decided the page (focusable-region violations), so they never reached the gate.
  - Once a cover is there, axe's reason is `bgOverlap`, not "partly obscured". So decision 3's reason could not be planted with a cover in the browser.
  - The judgement has no branch on that reason; it only makes the probe take three rows. Its unit case ("measures a text axe calls partly covered on its own surfaces when the probe finds nothing") holds it.
- **Not planted separately:** a cover on a sixth line box. The probe now takes every line box, all along it, and Q1's control shows the old sampling's miss.

## Runs
- **Run 1, in full at the T3b code, unplanted:** 33 failed.
  - Show as BPMN's 12 listings no longer found: its words now measure well on the task box (`--text-primary` on `--surface-panel`), so they come off.
  - 27 new findings, listed:
    - **case (boards):** a label where an item's "⟶" handle lies over its words, 20;
    - **shell:** text an open menu's shadow reaches (places, needs-you), 7.
  - `a11y/contrastFindings.json` now holds 84 looks and 147 findings.
- **Confirming run:** RESULTS.

## Carries closed
- **CARRIES row 110** (Show as BPMN's task box): measured, passes, listing off.
- **CARRIES row 121**, item by item:
  - sampling and the partly grid: Q1;
  - SVG `fill`: Q7;
  - `-webkit-text-fill-color`: read, not planted;
  - the cap before the product: V3;
  - gradientSurfaces' reason: V5;
  - a descendant's background: Q6;
  - an SVG root's filter, border or shadow and a pseudo-element's border or words: read, not planted;
  - outer shadow: Q5;
  - inert: Q4;
  - the page: V2;
  - decision 3: as above;
  - the findings shape: V4;
  - U15: now `color(srgb …)`.
