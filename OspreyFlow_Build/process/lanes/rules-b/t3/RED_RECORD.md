# rules-b · T3 · red record: undecided colour contrast gated (10 November 2026)

All runs were local, in the orchestrator's slot, on closed port 5184 with no Docker. Every plant was restored after its run.

## The gap
axe-core leaves `color-contrast` *incomplete*, never violated, when it cannot find the text's background:
- inside a fixed, transformed overlay;
- for text whose colour equals its background (1:1), which it reads as deliberate hiding.

`every-harness.spec.ts` read only `violations`.

## The measure (`a11y/undecidedContrast.ts`)
- Each node axe leaves undecided is measured: its colour is composited over its own ancestors' backgrounds.
- A gradient is checked at each of its colours, and the worst counts.
- The threshold is 4.5:1, or 3:1 for large text.
- A shortfall fails. So does a node it cannot measure: a picture (`url()`), an unread colour, or a node in a frame.
- Main's findings are listed with their owner, and a listed one that has gone fails.

## Red, at the real call site, in the shape the code emits
- **P1, the L2.11a dialog plant** (`.show-as-bpmn` text at `--surface-raised`): red in 6 of 6 looks
  (`rule-standards-harness` `open=1` and `open=1&file=other`; dark, light and GOV.UK). Every text in it measured 1.00:1.
- **P2, platform-b's P6 plant** (`.map-controls__state` at `--surface-panel`, 1:1): red in 3 of 3
  (`map-view-harness gazetteers=added`), also in light, where the listed attribution finding is excused. So the list
  excuses only its own node.
- **P3, the stale check**: the attribution chip given a token surface (`MapView.tsx`), so the listed finding
  is gone. Red: "listed contrast findings no longer found".
- **P4, the sibling path in the harness app** (`.summary-rail__status` at `--surface-raised`): red in 34 of 34
  (`harness/a11y` `a11y.spec.ts` and `install-page.spec.ts`), through the module imported by path.
- `canvas-focus.spec.ts` has the same call and no plant of its own.

## The measure's first form, corrected before it was trusted
Refusing every background image also caught `case-screen-options-harness` (12 looks). The case screen's canvas
grid is two CSS gradients over `--surface-sunken`, not a picture. Measured at each gradient colour,
"Canvas (stand-in)" passes, so it was decided, not listed.

## Runs
1. Plants P1 and P2: 9 failed, as above.
2. every-harness in full on main's tree, unplanted: 678 passed, 24 failed.
   - 12 were the gradient case, now decided.
   - 12 were the map attribution in light, now listed.
3. After the gradient measure and the listing, P1 and P2 again, then P3: red.
4. Final every-harness in full: **945 passed, 0 failed** (13.8 min, including the 2.5.3 cases).
5. Siblings:
   - workspace `a11y.spec.ts` and `canvas-focus.spec.ts`: 12 passed, after listing one finding;
   - harness a11y: 34 passed.

## What it newly finds on main (listed, not fixed; the owner carries each)
- **Platform (the map):** `MapView.tsx`'s attribution chip is `--text-secondary` on a raw `rgba(0,0,0,0.4)`. That is
  2.85:1 in the light theme, in all 12 map-view states.
- **Design system:** the warning toast's glyph is `--warning` on the toast, 4.41:1 in the light theme
  (`a11y/showcase.html`). It is `aria-hidden`, beside the toast's words. Holding it to 1.4.11's 3:1 instead is
  the owner's call.

## Limit, stated in the code
What lies under a node only by position, such as map tiles under an overlay, is not its ancestor and is not
seen. The measure reads the node's own surfaces.
