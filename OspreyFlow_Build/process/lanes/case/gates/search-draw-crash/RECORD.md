# search-draw-crash: the Glass's whole-tree crash on the canvas

**The defect.** `GlassCanvas` built Sigma on the same element React draws the canvas's toolbar, menus, overlays and selection bar into. `sigma.kill()` empties its container (sigma 3.0.3: `while (container.firstChild) container.removeChild(container.firstChild)`). The App mounts under `<StrictMode>` (`src/main.tsx`), so in every dev build the Sigma effect runs, is cleaned up and runs again on mount. That cleanup stripped React's children out of the canvas while React still held them.

The next node React inserted among them threw `insertBefore`, and React threw away the whole tree. The first such node was the radial menu on `\`. The page was left blank, with `#root` empty and focus on `<body>`.

- **Who it hit:** the live tier and DEMO_GUIDE §3.6's `npm run dev`.
- **Production builds:** they don't run StrictMode's double effect. The one production path that gives the canvas a new graph while mounted, a saved view, remounts the canvas by key.
- **Why the harness never saw it:** the keyboard harness mounted without StrictMode.

It was first taken for a large expansion, because A12 crashes after choosing `HMP-0003`. The page's own errors and its tree (no children under the canvas) showed it was the menu.

**The fix (32b340a).** Sigma draws in an empty child element of its own (`sigmaContainerRef`), which React renders nothing into. So `kill()` can only clear Sigma's canvases.

## Red, then green

| Check | Before the fix | After |
|---|---|---|
| `keyboard/canvas-strict-mode.spec.ts`, the harness at `?strict=1` | Red: the canvas's "Canvas tools" toolbar is not found | Green: the toolbar is there, `\` opens the menu, and the page raises no error. A second case shows the usual mount unchanged |
| A12 live (HMP fixture, stack g, Vite's dev build) | Red at 86af88e: `insertBefore`, `#root` empty (`a12-live-red.86af88e.log`) | 32b340a: the menu opens and the crash is gone; the spec's own drift (link types by name) came next (`a12-live.32b340a.log`). db36afe: A12, A13 and A15 all pass, 3 of 3 (`a12-live.db36afe.log`) |

A12's last two steps were the spec's own drift, each fixed in its own commit:
- the expansion is found under *Expand by link type* by the type's name as people read it ("Associate of (8)");
- the folded Metrics panel is unfolded (`live.ts`'s `unfoldSidePanel`, also used for the query builder).

## Gates at 32b340a, run here

- **Keyboard suite:** 866 passed, 1 skipped, 2 failed. Both failures are the known sources-connectors flake, which moves between that file's cases: this time `:144` and that file's registry check.
- **vitest:** 3,427 of 3,427 passed.
- **tsc:** clean.
- **Live, on stack g:** the lease was taken at 09:38Z under the orchestrator's grant, and the stack was brought down and released afterwards.

## Carried

- *Promote the expansion to a batch job*, the third of the cap's choices: a CARRIES row, waiting on the owner's ruling. It is a gap that already ran across the whole product.
- The other two choices on the expand refusal (narrow by link type, save as a view) are their own step. Its case, `keyboard/canvas-expand-cap.spec.ts`, is written and red, and not on this branch.
