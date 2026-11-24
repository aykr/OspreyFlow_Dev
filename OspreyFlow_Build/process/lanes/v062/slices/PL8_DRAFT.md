# SUPERSEDED on 24 November 2026: the owner ruled the five points; the first slice is `slices/PL8a.md` (this paper is kept as the record of the questions). PL8: the panel frame for the pages, in plain TypeScript: was a DRAFT (the conductor, the night of 23 November 2026)

**The owner asked for a part for every build whose needs are met. PL8's needs (PL3, PL4, PL9, PL10) are met on the plan's terms, but a read-only scout found two conflicts between the plan's text and the specification and a gap in PL9. They are the owner's, so no row is written and no builder can start.**

## What the plan says

"A panel frame for the pages, in plain TypeScript with no React: all ten panel actions of today's workspace (show and hide a side panel and the timeline, full width, fold, reorder, set a panel's width and height, raise and lower the timeline, Details from the keyboard), remembered after a reload and keyboard-tested as today's is." The owner's ruling of 20 November: the GOV.UK pages stay as close to the Default theme as plain TypeScript allows; only the light/dark switch is dropped (ADR-070 Amendment 1). `RULINGS.md` says PL8 is three slices and that `frame-scroll.spec.ts` is in scope.

## The rulings it needs (the scout's list)

1. **Persistence across a reload.** `OspreyFlow_Build/spec/02_GLASS_FRONTEND.md` about lines 315 to 321 says the choice "belongs to the browser tab: it is not stored, and each panel opens in its normal state on reload", which contradicts "remembered after a reload". Lines 323 to 339 (reorder and fold) say "kept in this browser". **Which holds for each of the ten actions?** (A genuine spec conflict: an edit to `spec/02` is the fix, an ADR if it is a real decision.)
2. **The minimum side width:** `spec/02` about lines 369 to 377 says "at least 240 pixels"; the code's `MIN_SIDE_WIDTH` is 300 (`OspreyFlow_Core/packages/glass-shared/src/layout/layoutSizes.ts` about line 14). Which wins?
3. **Scripts-off behaviour of the ten actions** (ADR-152 invariant I7: every page works with scripts off; a panel action is script-driven by nature). What does a scripts-off page show: all panels open and no controls, or a no-script form for each?
4. **Whether `frame-scroll.spec.ts` is in scope** (`RULINGS.md` says yes; confirm).
5. **PL9 is only part merged.** PL9a is on main; the plan's PL9 has a second part (the page service's sign-in round trip) that is not cut. PL8 needs PL9 on the plan: accept PL9a alone, or wait?

## The first slice, once ruled (the scout's proposal)

**Storage and logic first, no page:** the plain helpers already in `OspreyFlow_Core/packages/glass-shared/src/layout` (`sidePanelState.ts`, `layoutSizes.ts`, `panelOrder.ts`; the action ids in `packages/glass-shared/src/keyboard/actionRegistry.ts` about lines 1300 to 1312) plus a vanilla store (ADR-152 decision 3: one panel pattern; no inline style, decision 8) and one attach-style module with a delegated `data-action` listener. Acceptance: a keyboard spec in the pages app, one case per action id (rule 13), plus `test_functions_yaml.py` for the `panel-frames` row in `OspreyFlow_Core/apps/pages/FUNCTIONS.yaml` (about lines 345 to 352, "planned"). **React originals to read, not to copy** (they use inline style throughout): `OspreyFlow_Core/apps/workspace/src/layout/PanelFrames.tsx`, `Sash.tsx`, `SidePanelStack.tsx`. The workspace's own walkthrough `OspreyFlow_Core/apps/workspace/keyboard/panel-frames.spec.ts` (ten cases, `assertAllCovered`) is the model and must stay green. It must not touch `apps/workspace`.

**Access control:** a pure layout module has none; the usual tests for any page that reads `/v1` apply to the pages that mount it.
