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


## The server round: the probe judged alike on every platform (11 November 2026, 9c6b9dc)

**Why.** The merger's browser runs on the test server (20261111T091740Z on the merged tree, T093929Z on d41df45, slot 13) were red where the Mac's slot 9 had been green. All the new findings were the probe's own "not measurable". The UI font falls back to `system-ui`, so Linux Chromium sets the words a few pixels differently, and three of the probe's decisions turned on those pixels:
- **a shadow's reach.** Show as BPMN's panel ends at x 940 and its shadow (`0 8px 24px -8px`, 0.7 black) reaches "Expires" at x 941 on Linux only;
- **an open menu over the words.** Places' views menu covers part of the banner on Linux, and the first point inside the shadow's reach named the shadow;
- **whether the probe scrolled.** The derive preview's cell lies past its `overflow: auto` box (right edge 1184, words from 1221). The old probe scrolled only when the words crossed the viewport's edge, so the result turned on the font, and on what an earlier node had scrolled.

**What changed** (`undecidedContrast.ts`, `textContrast.ts`):
1. Another element's outer shadow is **measured** at each point. Its paint is a Gaussian with σ equal to half the blur (CSS Backgrounds 3), taken out to 3σ. The worst of three placements counts: laid away, straight under the words, or over them. The probe no longer fails on the shadow's reach.
2. A point where the words are **hidden** is not judged. The words are hidden under an opaque element that the browser's hit test finds over them (never one of their own descendants), or where a scrolling box clips them. (Words hidden at every point first passed with no ratio; the review round below makes them unmeasurable.)
3. Each node is **scrolled** to the middle of its boxes at once (`behavior: "instant"`), and every scroll position is put back after it.

**Red in Node** (`textContrast.test.ts`, 34 cases). Each fault was planted in `textContrast.ts` and then restored:
- **S1:** shadows ignored. Red: 3.
- **S2:** σ taken as the whole blur. Red: the coverage case.
- **S3:** the "over" placement dropped. Green at first, because no case had "over" as the worst. A case was added (a black shadow over light words on black), and then it was red.
- **S4:** the "under" placement dropped. Red: 1.
- **S5:** an unread shadow colour skipped. Red: 1.
- **S6:** no cap on shadows. Red: 1.
- **H1:** hidden points judged. Red: 2.
- **H2:** words hidden everywhere made unmeasurable. Red: 1.

**Red in the browser, at the real call site** (`checkUndecidedContrast` on real axe results). These ran on the server, slot 13, at the tree committed as 9c6b9dc. The log is `t3b/server-round-plants.txt`; "old" is the probe at d41df45.
- **A shadow in the words' own colour** reaching Show as BPMN's "Start": red at **2.14:1, a ratio**. The old probe gave "not measurable".
- **The platform shift in miniature:** a box with Show as BPMN's own shadow, the words 0 to 30px past it.
  - The old probe is red at every gap, and *which* words are red changes with the gap (3, 2, 2, 2, 1, 1, 1, 1).
  - The new probe is green at every gap.
- **An opaque cover over half of "If a Person meets":** green, the visible half measured.
  - Control: the same with `hides` removed is red, "over or under div".
  - A translucent cover (alpha 0.9) stays red in every variant.
- **The covered half's words in the cover's colour** (the visible half at 1:1): red at **1.00:1**. A hidden half never excuses the visible one.
- **An opaque descendant of the words' own cell** over half of its words: red, "over or under span".
  - Control: with the descendant guard removed it is green, so the guard carries it.
  - Found on the way: Chrome's hit test found the span 0.4px outside its fractional box, so the cover test now allows the 1px the browser snaps to.
- **The derive preview's cell, as loaded:** green, where the old probe is red.
  - It is red again only with `hides`, the clip check and the instant scroll all removed. Any one of the three settles it.
  - Scrolled right first, it is green in every variant.
- **A rounded corner** (60px) over the words: green in the new probe.
  - Chrome's hit test leaves out the corner past its arc, so the words there show no cover.
  - The probe's own corner test is a second guard behind the hit test, and this plant does not reach it.

**Carried, not closed** (CARRIES row 121, added to the earlier list):
- a shadow under a translucent ancestor, which is measured as straight under the words or away, never between;
- a shadow's rounded corners, taken as square (which can only overstate the paint);
- the corner test not reached in the browser.

### The review round (8bd3eef): the lane-reviewer's findings and the orchestrator's condition

**The orchestrator's condition:** hidden points are a new way for the probe to stay silent, so show that they cannot hide a real failure. Three changes, each measured below.
- **Words hidden at every point are now unmeasurable**, never a pass.
- **A cover hides the words only when nothing on its way up makes it see-through:** no filter, blend, mask or clip on it or any ancestor. Chrome's hit test ignores a mask.
- **The clip check is narrower.** A hit-test miss counts as hidden only where an ancestor that clips its overflow also leaves the point out. Any other miss is a cover: a modal's inertness, a rotation, pointer events kept off. A point where the browser hit-tests nothing (outside the viewport) is a cover too.

**The lane-reviewer's findings on 9c6b9dc, and what was done:**
1. *No record of the red runs:* written above, and the plant logs are in `t3b/server-round-plants.txt`. The browser plants and their variants stay out of every commit, as in every earlier round (Q1 to Q7, MP1 to MP3).
2. *A filter, blend or mask on a cover's ancestor:* fixed, as the second change above. Plants: a mask that clears the cover, and a cover in a blended wrapper. Both red.
3. *Hidden at every point passing:* fixed, as the first change above (H2′).
4. *Three placements are not the worst:* a shadow is now laid at every place in the words' chain, as well as away and over everything. A search over random colours found a case where only "between the layers" is the worst (1.04:1, against 1.13:1 over everything). It is a unit case, and S7 is red.
5. *σ unchecked:* measured from Chromium's pixels on the server. A first fit (run 20261111T130711Z) put σ at about 0.52 × blur, which refutes the Skia figure the reviewer half-remembered (0.29 × blur + 0.5).
   - **Corrected in the second pass:** my first reading of that fit, "the model slightly overstates the tail", was wrong. The samples sat at pixel centres, and there the model fell short (0.149 against 0.157 measured at 12.5px for a blur of 24). The reviewer caught it.
   - Measured again pixel by pixel, inside the shape and out (run 20261111T132837Z, slot 13): the Gaussian of blur / 2 is at most 0.0136 of the colour short anywhere, for every blur from 4 to 60px.
   - So the coverage now carries a margin of 0.015 within 3σ (S8 red without it).
6. *An empty hit test:* now a cover.
7. *A smooth scroll restore:* every restore is instant.
8. *`1e-06px`:* read with its exponent.
9. *The colour regex copied into the browser half:* kept. A colour it cannot read still reaches `parseColour` and is refused (S5).
10. *The "none" placement:* "over everything" dominates it in every case searched. It is kept as a second line and is not separately red.
11. *The corner comment:* corrected.

**Red at the real call site** (run 20261111T130711Z, slot 13). The plants sit on Show as BPMN's "If a Person meets", whose words are in their task box's own fill, so they are 1:1 wherever they are seen.
- With no plant: 1.00:1.
- A translucent half (alpha 0.5), a half gradient (opaque, then clear), an opaque half at opacity 0.9, a content-box clip with the words in its padding, an opaque half under a mask that clears it, and an opaque half in a blended wrapper: each "not measurable: over or under div". All red.
- An opaque half in a wrapper at opacity 0.5, and a frame (clear background, opaque border): 1.00:1, red. The wrapper's stacking puts it under the dialog, so the words are seen whole.
- Opaque over every point: "not measurable: hidden at every point", red, with 1:1 words and with 7:1 words alike.

**The full set at 9c6b9dc** (20261111T124046Z) had 7 failed and 972 passed:
- 4 were the GOV.UK brand's `data-brand` not set within 5s, before the probe ran. All 4 passed on the retake.
- 3 were places' open menu, "over or under button.menu-panel__item". A menu's items lie over its opaque panel, so the probe now looks through everything over the words for a cover that hides them (8bd3eef).
- On the retake, places' GOV.UK look gave "hidden at every point" for its two listed menu findings. Their listings now give that reason (owner shell).

### The second review pass (896bbf7)

The lane-reviewer's second pass on 8bd3eef left three must-fixes, and found the σ reading wrong (item 5 above, corrected there).
- **The clip test walked DOM ancestors, not containing blocks.** An ancestor now counts as clipping only while nothing between it and the words is positioned out of flow (absolute or fixed), and only as a block box. Past either, a miss is a cover. This fails closed and is read, not planted: no plant could tell the two apart, because the words' miss is then a cover either way.
- **Three branches had no red record.** They are recorded below, with one more the reviewer suspected.
- **The placement cap with a deep tree:** a shadow is now laid only where a layer paints. 25 clear wrappers under three shadows stay measurable (S9 red, which lays at every place).
- **Places' GOV.UK "Case: Kestrel":** it was gone in the full run at 8bd3eef but matched in the targeted retake. At 896bbf7's tree it measured 17.15:1 in 5 runs of 5 (20261111T132837Z), so its listing comes off.

**Red at the real call site** (run 20261111T133014Z, slot 13). Each plant was run against the new probe and against the probe with one branch removed.
- **The look-ahead:** a menu (an opaque panel with a clear item and words of its own) over half of "If a Person meets".
  - New: it passes, with the visible half at its own 13:1.
  - Without the look-ahead: red, "over or under span".
- **The pseudo guard:** an element whose opaque box lies under the dialog raises a translucent `::after` over half of the words.
  - New: red, "over or under div.zz-under".
  - Without the guard: it **passes silently**. The guard carries it.
- **A hit-test miss as a cover:** `pointer-events: none !important` on the derive cell.
  - New: red, "td missed by the browser's hit test".
  - With every miss taken as hidden: red too, as "hidden at every point". Both fail closed, and the reasons differ.
- **The empty stack:** the task label run out past the viewport.
  - New: red, "nothing the browser hit-tests (a point outside the viewport)".
  - Without the branch: red through another cover (the drawing's end circle). The plant shows the branch's own reason but does not tell the two apart.

**Unit plants at 896bbf7** (36 cases), each red: S1 (4), S2, S3, S4, S5, S6, S7, S8 (no margin: 2), S9 (every place: 1), H1 (2) and H2.

### The third review pass (the margin tapered)

All three of the second pass's must-fixes were confirmed closed. The third pass raised one suspected fail-open and two minors.
- **The suspected fail-open:** an opaque container under the words, with a translucent child raised over them. Planted (run 20261111T135324Z, slot 13), it is not one. Chromium lists the child on top and the container below the words (`CHILD > WORDS > rect > svg > div > CONTAINER`), so the look-ahead never takes the container as hiding them. The words are red, "over or under div", with and without the look-ahead.
- **The cliff at 3σ:** measured by band of σ past the shape (same run), for blurs of 4 to 60px. Chromium lays at most this much over the Gaussian of half the blur:

  | Band past the shape | Most laid over the Gaussian |
  | --- | --- |
  | [−2σ, 0) | 0.0045 |
  | [0, σ) | 0.0136 |
  | [σ, 2σ) | 0.0109 |
  | [2σ, 3σ) | 0.0025 |
  | from 3σ | nothing at all |

  - So the 3σ cut-off is the renderer's own.
  - The margin is now 0.015 to 2σ, then falls straight to 0.0025 at 3σ. The step at 3σ is about 0.004 of the colour.
  - Unit plants: S10, the margin flat to 3σ, is red (the no-cliff case); S8, no margin to 2σ, is red (2).
- **The σ run's slot:** 20261111T132837Z ran in slot 13, now written in item 5.
- **The full set at 896bbf7** (20261111T133108Z): 975 passed, 4 failed, and all 4 failed before the probe ran, on the GOV.UK brand's `data-brand` not set within 5s. The harness set: 34 passed. The 4, with the 1 from 8bd3eef's run, passed on the retake (5 passed). A different set fails each run (4, 1, 4).
