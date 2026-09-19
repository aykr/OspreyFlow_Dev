/**
 * Phase 6a Stage 4's own resolution of `07_BUILD_PLAN.md`'s "Gaps with no owning phase" entry on
 * `keyboard.spec.ts`: that walkthrough was a hardcoded sequence with no auto-discovery, so a new
 * action with no case added was invisible to it — the stage assigned to build the stronger,
 * machine-checked fix, once the second keyboard-driven surface (the Dossier) made rule 13 alone
 * no longer defensible (`GlassCanvas.tsx` already had four actions no existing test covered,
 * checked directly, before this stage added anything).
 *
 * Each keyboard-driven surface exports a plain list of its own action ids; a `test()` that
 * actually proves one calls `registerCovered(id)` at the point it does so — call-site
 * registration, not title-regex matching against test names, which is brittle to a rename. A
 * final assertion checks every registered id was covered, failing with the exact missing ids
 * rather than passing silently.
 *
 * Module state, not a class instance, deliberately: `keyboard.spec.ts` runs its tests
 * sequentially in one worker (this project's own `keyboard/playwright.config.ts`), so this
 * module's state is shared across every test in the file — a `registerCovered` call in an
 * earlier test is visible to the final assertion in the last one. A parallel-worker config would
 * break this; if `playwright.config.ts` ever gains one, this file's own single-module assumption
 * needs revisiting first.
 */

const covered = new Set<string>();

export function registerCovered(id: string): void {
  covered.add(id);
}

export function assertAllCovered(actions: readonly string[]): void {
  const missing = actions.filter((id) => !covered.has(id));
  if (missing.length > 0) {
    throw new Error(
      `Keyboard action(s) registered with no proving test case: ${missing.join(", ")}`,
    );
  }
}

/**
 * `GlassCanvas.tsx`'s own keyboard-reachable actions. Pan, zoom and lasso are deliberately absent
 * — `keyboard.spec.ts`'s own header comment already names them as having no keyboard equivalent
 * in `02_GLASS_FRONTEND.md` §6's own text, the same exemption this registry inherits rather than
 * re-litigates. `overlay-dismiss-edge-inspection` is absent for the same class of reason, checked
 * directly rather than assumed: nothing keyboard-driven ever opens `EdgeInspectionOverlay` (only
 * Sigma's own mouse `clickEdge`/`enterEdge` events do), so a pure-keyboard walkthrough has no
 * all-keyboard path to reach the state this action would dismiss — the code itself is still fixed
 * (see `GlassCanvas.tsx`'s own `onKeyDown` guard) so a keyboard user who ends up there via a mixed
 * mouse-then-keyboard session isn't stuck, but this file cannot honestly claim to test entering
 * that state, so it does not claim to test leaving it either.
 */
export const CANVAS_ACTIONS = [
  "tab-establish-ring",
  "tab-cycle-ring",
  "arrow-walk-forward",
  "arrow-walk-backward",
  "space-toggle-ring-membership",
  "enter-expand",
  "backslash-open-menu",
  "menu-item-expand-by-edge-type",
  "menu-item-manual-link",
  "menu-item-manual-split",
  "menu-item-explain-cluster",
  "menu-item-view-messages",
  "overlay-dismiss-cluster-explain",
] as const;
