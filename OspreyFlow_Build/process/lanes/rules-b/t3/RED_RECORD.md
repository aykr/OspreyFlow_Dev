# rules-b · T3 · red record: undecided colour contrast gated (10 November 2026)

**The final form is 9e8d51a, round 3 (at the end).** The sections before it describe 46e53d3, and round 3 says what changed.

All browser runs were local, in slots the orchestrator granted, with no Docker. The final form's runs used `OSPREY_PORTS_SLOT=9`, at 46e53d3 as committed. Every plant was restored after its run.

## The gap
axe-core leaves `color-contrast` *incomplete*, never violated, when it cannot find the text's background:
- inside a fixed, transformed overlay;
- for 1:1 text, which it reads as deliberate hiding;
- over another element.

Every axe scan read only `violations`. That is every-harness, the workspace's `a11y.spec.ts` and `canvas-focus.spec.ts`, and the install harness's `a11y.spec.ts` and `install-page.spec.ts`.

## The gate, in its final form (46e53d3, after three reviews: mine and the orchestrator's of 9dab1ef, merger-c2's of bd9b4ef)

**The browser half, `a11y/undecidedContrast.ts`.** For each node axe leaves undecided it reads:
- computed styles up to `<html>`, with whether each element's box lies under the text;
- any painted absolutely or fixed positioned `::before`/`::after`;
- what `elementsFromPoint` finds over and under the text. During the probe a temporary style sheet gives every element pointer events. The probe checks the left, middle and right of up to five line boxes, or a 5 × 3 grid of each where axe saw part covered.
- the elements axe names as covering the text (`relatedNodes`). The text's own box or an ancestor's is a clip; anything else is a cover.

**The judgement, `src/color/textContrast.ts`.** It runs in Node, with 18 unit cases.
- Text is composited over every background it may stand on:
  - each gradient stop, plus 7 colours between neighbouring stops;
  - crossing gradient layers composited together;
  - an ancestor's opacity applied to its whole group;
  - nothing from an ancestor whose box is not under the text.
- The threshold is 4.5:1, or 3:1 at 24px, or at 14 × 4/3 px bold.
- These are unmeasurable, and so fail:
  - a painted element over or under the text that is neither the node, inside it, nor an ancestor (its background, a replaced element, a painted pseudo-element, a filter or blend);
  - axe's "partly obscured" unless what axe names is the text's own box or an ancestor's;
  - a filter, backdrop-filter or blend in the chain;
  - a colour it cannot read: anything but rgb/rgba, `color(srgb)`, oklab, oklch or `transparent`, and any `none` component;
  - a picture;
  - a node in a frame or shadow root;
  - axe's `pseudoContent`.
- A ratio that is not finite fails too.

**Listed findings** are keyed by test title and selector. One is excused only while its text matches and:
- for a measured finding, its ratio is no worse;
- for an unmeasurable one, its reason is exactly the same.

A listed finding no longer found fails. A listed title that is not a scanned look fails.

## Red in Node (`src/color/textContrast.test.ts`; each fault planted in `textContrast.ts`, then restored)
- **U1:** the bold threshold as 18.66px. Red at the assertion that 18.66px bold is held to 4.5:1 (`needFor("18.66px", "700")`), in the 18.67px case's test.
- **U2:** the gradient's colour list without oklab and its kin. Red: 3 cases.
- **U3:** the overlap ignored. Red: 2 cases.
- **U4:** an ancestor's opacity ignored. Red: 1.
- **U5:** a `none` component read as NaN. Red: 1.
- **U6:** no colours between stops. Red: 1.
- **U7:** layers not composited where they cross. Red: 1.
- **U8:** an ancestor's box not under the text still laid under it. Red: 1.
- **U9:** axe's "partly covered" with nothing probed passed. Red: 1.
- **U10:** a listed reason matched by `includes`. Red: 1.
- **U11:** "partly covered" never failing. Red: 2.
- **U12:** a clip never explaining it. Red: 1.
- The final ratio guard cannot be reached by a test while `parseColour` refuses non-finite parts. It is kept as a second line.

## Red in the browser, at the real call site, against 46e53d3 as committed
- **P1, the L2.11a dialog plant** (`.show-as-bpmn` text at `--surface-raised`): 6 of 6 red, every text at 1.00:1 (axe: `equalRatio`).
- **P2, platform-b's P6 plant** (`.map-controls__state` at `--surface-panel`): 3 of 3 red, at 1.00:1. The listed map chip stayed excused.
- **P3, the stale check** (the chip given an opaque `--surface-panel`): 3 of 3 red, "listed contrast findings no longer found as listed".
- **P5, the gradient** (`--grid-line` as `color-mix(in oklab, var(--text-secondary) 100%, transparent)`): 3 of 3 red. "Canvas (stand-in)" measured 1.00:1 (axe: `bgGradient`).
- **M1, a foreign overlay with `pointer-events: none`** (a sibling `div` laid over the map, z-index 1000, in `MapView.tsx`): 3 of 3 red. The panel's words were "over or under div" (axe: `bgOverlap`). The 9dab1ef and bd9b4ef probes lifted only the node's own chain, so they could not see it.
- **M2, a `none` component:**
  - First, `.map-controls__state` in `oklch(0.5 0 none)`. axe decided it itself, because Chrome draws `none` as 0: a violation in dark and a pass in light and GOV.UK. It never reaches the gate.
  - Then the dialog's text in `oklch(from var(--surface-raised) l c none)`, which axe leaves undecided: 3 of 3 red, "an unread colour oklch(… none)". Before the fix, that was NaN and passed.
- **S1, the workspace showcase** (`.toast` words at `--surface-raised`, `a11y.spec.ts`): 2 of 2 themes red.
- **S2, the canvas harness** (`.canvas-toolbar__label` at `--surface-panel`, `canvas-focus.spec.ts`): red.
- **S3, the harness app** (`.summary-rail__status` at `--surface-raised`): 34 of 34 red.

## Corrected on the way, before being trusted
- **First form (9dab1ef):** refusing every background image caught the canvas grid, which is a CSS gradient. It then dropped the grid's `oklab()` stop, so the canvas's "decided" pass was unproven (the reviews).
- **Fix pass (7ce19d0):** the probe lifted only the node's own chain, which merger-c2 found.
- **Final form:**
  - Failing every "partly obscured" closed failed seven truncated or off-screen texts (the account name, a table cell, Home's case list, "Save and load" past the viewport).
  - axe's own `relatedNodes` named the text itself or an ancestor in every case: clips, not covers. So a clip that axe itself names is measured, and anything else stays closed.
  - An overflow heuristic tried first was wrong. It ran after `scrollIntoView` had moved the text.

## Runs (final form)
- Targeted, unplanted, at 46e53d3's code: 86 passed.
- Plants as above.
- In full, at 46e53d3: workspace 927 passed and 40 failed; harness app 34 passed.
  - The 40 were new findings of the final probe, listed in the next commit (boards, metrics, views); the gate's code did not change.
  - Those 40 looks then passed as listed (the run matched 52 titles in all; the other 12 passed already).
  - So the whole of every-harness and the siblings is green: 967 plus 34.

## What it finds on main (listed, not fixed; carried by owner: the map chip, toast glyph, key cap and shell's two are in CARRIES; the boards', metrics' and views' rows are added by merger-c2 at merge)
- **Platform (the map):** `MapView.tsx`'s attribution chip is `--text-secondary` on a raw `rgba(0,0,0,0.4)`, over the map's canvas. It is unmeasurable in every theme and state: "over or under canvas.sigma-mouse".
- **Design system:** the warning toast's glyph is `--warning`, 4.41:1 in light (`a11y/showcase.html`). It is `aria-hidden`, beside words; whether 1.4.11's 3:1 applies is the owner's call.
- **Home:** the start page's key cap "G" (`.home-key`, `opacity: 0.8`) is 4.12:1 in light and 3.92:1 under GOV.UK, on the primary button.
- **Shell (places):** More views, drawn open under GOV.UK, lies over three of the banner's words.
- **Case (L3.3, the boards):** the board's link lines are one SVG over the board, so each item's "⟶" handle and the photo's label are over or under it, as are the blank board's words. Unmeasurable in every theme, in each board state.
- **Rules (the metrics panel, since the split) and case (views):** the rarity note, and the delete question under GOV.UK. axe reads each as partly covering another element and names none, and the dense probe finds nothing either. They are kept closed.
- **Shell (L2.3's prototype variant b):** the rail's "⋯" sits on a transparent button over the rail, or over the GOV.UK banner.

## Limit, stated in the code
The probe samples points across the text, not every pixel: the left, middle and right of up to five line boxes, spread first to last. A cover lying wholly between them passes unseen. That includes a partly covered text, since the 5 × 3 grid for those was dropped in round 3. It is carried to T3b with merger-c2's other carries.


## Round 3, the final form (9e8d51a): merger-c2's review of e94b18c

**What changed in the judgement (`src/color/textContrast.ts`)**
- Surfaces are judged per probed point (`covers: boolean[]`). Text spilling past its box counts on both surfaces.
- Each gradient layer keeps the colour beneath it as a sample.
- A `none` layer is skipped.
- More than 20 000 possible backgrounds is unmeasurable.
- A colour out of range (`rgb(-1000 …)`) is unread.
- An unmeasurable judgement carries `ownRatio`, what its own surfaces give, and a listing of it is pinned to that as a floor.
- The dead `gradientColours` is gone.

**What changed in the probe (`a11y/undecidedContrast.ts`)**
- Points are the left, middle and right of up to five line boxes, spread first to last.
- An SVG paints only through its shapes.
- A foreign element's own words at the point, its inset shadow or its border band count.
- The clip classification is gone, and axe's `relatedNodes` are no longer read.

**axe's "partly obscured" (REPORT decision 3)**
- Failing it always closed, merger-c2's suggestion, failed 174 looks in the browser. Nearly all were text below the fold or past a scrolling box (the help page, Home's cases, admin tables).
- It is measured when the probe finds nothing foreign at its points. merger-c2 accepted that.
- The residual, a cover wholly between the probed points, is carried for T3b.

**Red in Node** (22 cases; each fault planted in `textContrast.ts`, then restored):
- **U13:** no colour beneath a layer. Red: 2.
- **U14:** covers all-or-nothing. Red: the spill case.
- **U15:** no range check. Red: 1.
- **U16:** a `none` layer kept. Red: 1.
- **U17:** no cap on the spread. Red: 1, with four layers. Six layers had crashed the run rather than failed it.
- **U18:** the own-surface pin ignored. Red: 1.
- **U19:** partly-covered never measured, under the always-closed rule then in force. Red: 2. The rule itself was then replaced by decision 3.

**Red in the browser, against 9e8d51a as committed (`OSPREY_PORTS_SLOT=9`)**
- **MR1, merger-c2's spill** (the dialog's title `width: 40px; white-space: nowrap; background: var(--text-primary)`): 3 of 3 red at 1.00:1 (axe: `equalRatio`).
  - The control proves the branch: with `covers` put back to all-or-nothing, the same plant passes 3 of 3.
  - A first form with a near-equal box colour was decided by axe itself as a violation, so it never reached the gate.
- **MR2, merger-c2's sized gradient** (the title on `var(--text-primary) linear-gradient(var(--surface-raised), …) 0 0 / 1px 1px no-repeat`): 3 of 3 red at 1.00:1 (axe: `bgGradient`).
- **TT, a listed title mistyped** in `contrastFindings.json`: the title check red, naming it.
- **P1** 6 of 6; **P2** 3 of 3; **P3** 3 of 3 (stale); **P5** 3 of 3; **M1** 3 of 3, "over or under div"; **M2b** 3 of 3, "an unread colour oklch(… none)".
- **S1** 2 of 2; **S2** red; **S3** 34 of 34.

**Runs**
- The full workspace run at the round-3 code, before the listings were rewritten: 86 failed.
  - 10 were old listings that now pass: the blank board, Bob's label, the metrics rarity note, the views delete question.
  - The rest were findings to re-pin or new.
- With `a11y/contrastFindings.json` (84 looks, 132 findings): workspace 967 passed, harness app 34 passed.

**What it finds on main, final (`a11y/contrastFindings.json` and `SHOWCASE_CONTRAST_FINDINGS`)**
- **Platform:** the map's attribution chip lies over the map canvas, in every state and theme. Its own surfaces give 11.31:1 in dark, 2.85:1 in light and 6.88:1 under GOV.UK.
- **Shell:** variant b's ⋯ over the rail or banner; places' open More views over the banner's words under GOV.UK.
- **Case (boards):** a handle where a link line runs under it, and the photo's handle and label where they overlap.
- **Rules-b (Show as BPMN, L2.11a's own):** the drawing's words on the task box, in the dialog and in the rule editor. CARRIES row under rules-b.
- **Home:** the key cap at `opacity: 0.8`, 4.12:1 in light and 3.92:1 under GOV.UK. It is fixed on lane/rules-hyg at dd60c52; the listing comes off when both land.
- **Design system:** the warning toast's glyph, 4.41:1 in light.
- **Outside T3's reach:** a pressed (`:active`) primary button in dark at 3.59:1 (rules' measurement). No scan presses a button. A harness state, or the token pair checked directly, is T3b's.
