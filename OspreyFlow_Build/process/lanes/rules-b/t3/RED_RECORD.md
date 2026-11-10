# rules-b · T3 · red record: undecided colour contrast gated (10 November 2026)

All browser runs were local, in the orchestrator's slot. They used port 5190, through an untracked override config, because studio's worktree held 5184. No Docker. Every plant was restored after its run.

## The gap
axe-core leaves `color-contrast` *incomplete*, never violated, when it cannot find the text's background:
- inside a fixed, transformed overlay;
- for 1:1 text, which it reads as deliberate hiding;
- over another element.

Every axe scan here read only `violations`. That is every-harness, the workspace's `a11y.spec.ts` and `canvas-focus.spec.ts`, and the install harness's `a11y.spec.ts` and `install-page.spec.ts`.

## The gate (final form, after both reviews of 9dab1ef)
**The browser half, `a11y/undecidedContrast.ts`.** For each undecided node it reads:
- its computed styles up to `<html>`;
- any painted absolutely or fixed positioned `::before`/`::after`;
- what `elementsFromPoint` finds at three points on its text. The node and its ancestors take pointer events for the probe, and their inline values are put back afterwards.

**The judgement, `src/color/textContrast.ts`.** It runs in Node and is unit-tested.
- Text is composited over every background it may stand on: each gradient stop is a separate background, and an ancestor's opacity applies to its whole group.
- The threshold is 4.5:1, or 3:1 at 24px, or at 14×4/3 px bold.
- These are unmeasurable, and so fail:
  - a painted element that is neither the node nor an ancestor, before the first opaque ancestor;
  - a filter, backdrop-filter or blend;
  - a colour it cannot read (anything but rgb/rgba, `color(srgb)`, oklab, oklch or `transparent`);
  - a picture;
  - a node in a frame or shadow root;
  - axe's `pseudoContent`.
- axe's reason (`messageKey`) is kept in every message.

**Listed findings** are keyed by test title and selector. One is excused only while its text matches and its ratio is no worse, or, for an unmeasurable one, while it gives the same reason. A listed finding no longer found fails.

## Red, in Node (`src/color/textContrast.test.ts`, 13 cases; each fault planted in `textContrast.ts`, then restored)
- **U1:** the bold threshold as 18.66px. Red: 3.01:1 at 18.67px bold.
- **U2:** the gradient's colour list without oklab and its kin. Red: 3 cases (the canvas grid as Chrome computes it, a stop the colour of the text, an unread stop).
- **U3:** the overlap ignored. Red: 2 cases.
- **U4:** an ancestor's opacity ignored. Red: 1 case.

## Red, in the browser, at the real call site in the shape the code emits
- **P1, the L2.11a dialog plant** (`.show-as-bpmn` text at `--surface-raised`): 6 of 6 red. Every text in the dialog measured 1.00:1 (axe: `equalRatio`).
- **P2, platform-b's P6 plant** (`.map-controls__state` at `--surface-panel`): 3 of 3 red, the panel's words at 1.00:1. The listed map chip stayed excused, so the list excuses only its own node.
- **P3, the stale check:** the chip given an opaque `--surface-panel`. It measured fine, so only "listed contrast findings no longer found as listed" fired, 3 of 3.
- **P5, the gradient at the real call site:** `--grid-line` as `color-mix(in oklab, var(--text-secondary) 100%, transparent)`, which Chrome computes as an `oklab()` stop. Red 3 of 3: "Canvas (stand-in)" at 1.00:1 (axe: `bgGradient`). The first form (9dab1ef) dropped this stop, which the reviews found.
- **P4, the harness app's sibling scans** (`.summary-rail__status` at `--surface-raised`, first form): 34 of 34 red.

## Runs
- **A, targeted, unplanted:**
  - The map chip was unmeasurable in all 36 looks: over `canvas.sigma-mouse` (axe: `imgNode`). The first form had passed it in dark and GOV.UK by measuring its ancestors.
  - The case screen's variant b showed "⋯" over `nav.left-rail`, or the GOV.UK banner, on a transparent button.
  - Both are listed.
  - After the pointer-events fix to the probe: 65 passed.
- **B:** P1, P2, P3 and P5 as above.
- **C, in full:**
  - every-harness with the workspace siblings: 949 passed and 9 failed. The 9 were new findings of the stricter measure, now listed (Home's key cap; places' open menu under GOV.UK). The 9 titles then passed as listed.
  - Over the whole of C, 958 are green.
  - The harness app's a11y: 34 passed.

## What it newly finds on main (listed, not fixed; each in CARRIES with its owner)
- **Platform (the map):** `MapView.tsx`'s attribution chip is `--text-secondary` on a raw `rgba(0,0,0,0.4)`, laid over the map's canvas. It is unmeasurable in every theme and state (2.85:1 on its own surfaces in light).
- **Design system:** the warning toast's glyph is `--warning`, 4.41:1 in the light theme (`a11y/showcase.html`). It is `aria-hidden`, beside the toast's words; whether 1.4.11's 3:1 applies is the owner's call.
- **Home:** the start page's key cap "G" (`.home-key`, `home/home.css`) is drawn at `opacity: 0.8`. On the primary button that is 4.12:1 in light and 3.92:1 under GOV.UK (start-harness's three states, alert-figures' `home=1`).
- **Shell (places):** the top bar's More views, drawn open under GOV.UK, lies over the notification banner's words. They are unmeasurable: what is under them is the menu.
- **Shell (L2.3's prototype variant b):** the rail's "⋯" More glyph sits on a transparent button laid over the rail, or under GOV.UK over the notification banner, so its background is not its own.

## Limits, stated in the code
- A foreign element with `pointer-events: none` is left out by `elementsFromPoint`. Only the node and its ancestors are lifted for the probe.
- The probe samples three points on the text, not every pixel.
