# rules-b · T3b · the contrast probe's limits, and Show as BPMN's task box (plan, 10 November 2026)

**From:** CARRIES rows 110 and 121. **Files:**
- `apps/workspace/a11y/undecidedContrast.ts`, `src/color/textContrast{,.test}.ts`, `a11y/contrastFindings.json` (ratified at T3);
- `src/alerts/ruleStandards/*` (mine, from L2.11a) if the task box needs a token change.

**Tests first, each red by a planted fault (rule 15).**

## The probe (`a11y/undecidedContrast.ts`)
1. **Points along the text, not three per box.**
   - Sample every 8px along each of the node's own text boxes, at mid-height. Where axe says partly obscured, take three rows (20%, 50%, 80%).
   - All line boxes, capped at 400 points per node. Over the cap, the node is unmeasurable.
   - Points come from the node's own direct text nodes, so a descendant's background under that text is seen.
2. **What paints, more fully:**
   - an SVG root's filter, border or shadow;
   - a pseudo-element painting by border or by text;
   - an outer box-shadow reaching the point from an element that is not an ancestor;
   - inert subtrees (their `inert` lifted for the probe and restored).
3. **The page under everything** is the browser's `Canvas` colour as computed, not white.
4. **SVG ink:**
   - SVG text is read from `fill` (and `fill-opacity`);
   - HTML text from `-webkit-text-fill-color` when it is set apart from `color`.
5. **SVG shapes under SVG text** (Show as BPMN's task box) are surfaces at that point, by their computed `fill` and `fill-opacity`, not covers. A shape over the text, or one whose fill cannot be read (a gradient or pattern `url(#…)`), stays a cover.

## The judgement (`src/color/textContrast.ts`)
6. **The pairs cap** is checked before each flatMap, from the product of the counts. `gradientSurfaces` says why it refused (a picture, an unread stop, too many backgrounds), and judge words each.
7. **The page colour** comes from the sample. Per-point under-surfaces lie between the text and its chain.
8. **`readFindings(json)`** checks the findings file's shape and throws naming the bad entry. every-harness loads through it.
9. **U15's case** becomes the shape Chrome really emits out of range (`color(srgb 4 0 0)`). `rgb()` stays refused as a second line.

## Browser plants (a slot), at the real call site
- a 400px-wide text with an `rgba(0,0,0,.6)` overlay over x 60–140 (merger-c2's);
- a cover on a sixth line box;
- a partly-obscured text (decision 3's branch) with and without a cover;
- an inert overlay;
- an outer shadow over text;
- a descendant's background under the text;
- SVG text whose `fill` is 1:1 with the task box;
- then every-harness, the siblings and the harness app in full, re-listing what the finer probe finds.

## Show as BPMN
Its listing comes off if the task box measures well. If it fails, the drawing's tokens are fixed in `showAsBpmn.css` (mine), red first.
