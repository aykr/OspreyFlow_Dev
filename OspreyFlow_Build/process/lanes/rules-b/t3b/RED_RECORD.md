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
- **Q7, the drawing's words in the task box's own fill:** 3 of 3 red, "End" at 1.00:1 (1.08:1 in one theme). merger-c2 noted that "End" sits on the dialog, not the task box, so this was red through the chain and is superseded by Q7′ below.
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
- **Confirming run at 6e18acc:** 975 + 34 passed. merger-c2's review then found three silent passes, and the fix pass follows.

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


## The fix pass for merger-c2's review of 6e18acc (375f2f6, 93a723f)

**The blockers, in the SVG under-path**
- It is now a fail-closed allowlist.
- Only a rect, circle, ellipse, polygon or path counts, and only:
  - where its colour fill covers the point (`isPointInFill`) and its stroke does not (`isPointInStroke`, in its own coordinates);
  - with no filter, mask or blend from it up to the ancestor it shares with the words.
- It is laid at that ancestor's place in the chain, with its own branch's opacities. Anything else (a line, an image, a `use`, another label's text, a stroke, a pattern fill) is a cover.

**The musts**
- Shadows' reach is taken per node after scrolling, by offset and spread.
- Past 600 probe points a node is unmeasurable (PLAN amended).
- `inert`'s own value is restored, and the colour probe is removed in a `finally`.

**Red in Node** (28 cases)
- **W1:** shapes laid at the words' own element. Red: the opacity case, 3.98:1.
- **W2:** no cap across the tree's layers. Red: 1.
- **V3′:** the gradient's count taken after building. Green, and honestly so. A count after each product also refuses by the fourth layer, so no result tells the two apart. The count before bounds only what is built, and the test's comment says that much.

**Red in the browser, at the real call site (Show as BPMN's drawing), against 93a723f**
- **MP1, merger-c2's case 1** (the words `fill:#000; opacity:.5` over a task `fill:#fff`): the task's words at 3.98:1 in all three themes, its real figure. The old layering gave 5.28:1.
- **MP2, a stroke-only task** (`fill:none`, a 60px stroke in the words' own colour):
  - where the stroke reaches the words, "over or under rect.show-as-bpmn__task";
  - where it does not, the words are measured on the dialog, 1.00 to 1.11:1.
  - Both are red. Unfilled geometry paints nothing, and the browser does not hit-test it.
- **MP3, a task at opacity .2** in the words' contrast colour, the words in the dialog's own surface: the task's words at 1.50 to 1.80:1, red. Ignoring the shape's opacity would give about 13:1.
- **Q7′, the task box in the words' own colour:** the task's words at 1.00:1 on the box, red through `under`.

**Re-listing at 375f2f6:** with the shadow's reach taken by offset and spread, the seven shell shadow listings are no longer found and come off (93a723f). Nothing new was found. `contrastFindings.json` holds 78 looks and 140 findings.

**Carried, not closed (CARRIES row 121):**
- the 5 × 3 grid where axe says `bgOverlap` (three rows are taken only for partly-obscured);
- a sixth line box, beyond what Q1's control shows;
- decision 3's own reason under a cover;
- the root background's spread over the canvas;
- a modal `<dialog>`'s inertness;
- the plant for `-webkit-text-fill-color`.

**Confirming run:** after "built".
