/**
 * Phase 6a Stage 4's own resolution of `07_BUILD_PLAN.md`'s "Gaps with no owning phase" entry on
 * `keyboard.spec.ts`: that walkthrough was a hardcoded sequence with no auto-discovery, so a new
 * action with no case added was invisible to it — the stage assigned to build the stronger,
 * machine-checked fix, once the second keyboard-driven surface (the Dossier) made rule 13 alone
 * no longer defensible (`GlassCanvas.tsx` already had four actions no existing test covered,
 * checked directly, before this stage added anything).
 *
 * Each keyboard-driven surface exports a plain list of its own action ids, declared via
 * `defineActionRegistry` below; a `test()` that actually proves one calls `registerCovered(name,
 * id)` at the point it does so — call-site registration, not title-regex matching against test
 * names, which is brittle to a rename. A final assertion in that surface's own spec file checks
 * every registered id was covered, failing with the exact missing ids rather than passing
 * silently.
 *
 * **Namespaced per registry, not one flat `Set<string>` — Phase 7 Stage 4's own fix.** A third
 * registry (`QUERY_BUILDER_ACTIONS`) exposed a gap the first two (`CANVAS_ACTIONS`,
 * `METRICS_PANEL_ACTIONS`) never had to answer: nothing stopped a `registerCovered` call in one
 * surface's spec file from satisfying a *different* surface's `assertAllCovered`, if their id
 * strings ever collided — the two existing files avoided it only because `CANVAS_ACTIONS` and
 * `METRICS_PANEL_ACTIONS` happen not to share a string, not because anything enforced it. Keying
 * `covered` by registry name closes that by construction: a call for the wrong registry can never
 * satisfy this one's assertion, regardless of what `playwright.config.ts` does with workers.
 *
 * **`defineActionRegistry` self-registers into `ALL_REGISTRIES`** so `check-registry-coverage.mjs`
 * (a plain Node script, not a Playwright test — see its own header) can enumerate every declared
 * registry by statically importing this module, and fail the build when one has no
 * `assertAllCovered` call reaching it anywhere under `apps/workspace/keyboard/*.spec.ts` — the gap
 * a purely runtime check cannot close, since nothing forces a *test* asserting a registry's own
 * coverage to exist merely because the registry itself does.
 */

export interface ActionRegistry {
  readonly name: string;
  readonly actions: readonly string[];
}

export const ALL_REGISTRIES: ActionRegistry[] = [];

export function defineActionRegistry<const T extends readonly string[]>(
  name: string,
  actions: T,
): T {
  ALL_REGISTRIES.push({ name, actions });
  return actions;
}

const covered = new Map<string, Set<string>>();

function coveredSetFor(registryName: string): Set<string> {
  let set = covered.get(registryName);
  if (!set) {
    set = new Set<string>();
    covered.set(registryName, set);
  }
  return set;
}

export function registerCovered(registryName: string, id: string): void {
  coveredSetFor(registryName).add(id);
}

export function assertAllCovered(registryName: string, actions: readonly string[]): void {
  const seen = coveredSetFor(registryName);
  const missing = actions.filter((id) => !seen.has(id));
  if (missing.length > 0) {
    throw new Error(
      `${registryName}: keyboard action(s) registered with no proving test case: ${missing.join(", ")}`,
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
export const CANVAS_ACTIONS = defineActionRegistry("CANVAS_ACTIONS", [
  "focus-establishes-ring",
  "tab-leaves-the-canvas",
  "ctrl-arrow-cycles-ring",
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
  // Phase 7 Stage 5 (the pathfinder) — `07_BUILD_PLAN.md`'s own keyboard-walkthrough entry drew
  // the line this follows: a further canvas radial-menu item extends this registry rather than
  // getting its own, the same shape `menu-item-manual-link`/`explain-cluster` already are.
  "menu-item-find-paths",
  "path-selector-cycles-highlighted-path",
  "overlay-dismiss-pathfinder-result",
  // A failed `/v1/paths` call is a distinguishable state from a completed zero-result search
  // (`GlassCanvas.tsx`'s own `pathError`/`pathResult` split) — its own dismiss action, proven the
  // same way `overlay-dismiss-pathfinder-result` already is.
  "overlay-dismiss-pathfinder-error",
  // `expandNode`/`manualAssertion`/`explainCluster` used to drop a failed call silently — fixed
  // to a shared `ActionErrorOverlay`, one dismiss action for all three
  // (`ActionErrorOverlay.tsx`'s own doc comment has the reasoning for why one overlay, not three).
  // Proven via manual link/split, the priority fix (a failed write, not a failed read) — and via
  // expand and explain-cluster too, since each reaches the same overlay through a different
  // existing keyboard action.
  "overlay-dismiss-action-error",
] as const);

/**
 * `metrics/MetricsPanel.tsx`'s own keyboard-reachable actions — Phase 7 Stage 3, a second and
 * separate keyboard-driven surface from `GlassCanvas`'s own `CANVAS_ACTIONS`
 * (`keyboard/metrics-panel-harness.tsx`'s own docstring has the full reasoning for why this is a
 * new list rather than an addition to that one). The metric selector, compare toggle and hull
 * toggle are deliberately absent: each is a plain `Select`/`Toggle` with no custom key handling of
 * its own, the same "a native control needs no proving test case" exemption
 * `resolution/ThresholdControl.tsx`'s own docstring already establishes for its `<input
 * type="range">` — only "select a row" is real, canvas-touching application logic (a camera pan
 * via `GlassCanvasHandle.focusOnNode`), which is why it alone is listed here.
 */
export const METRICS_PANEL_ACTIONS = defineActionRegistry("METRICS_PANEL_ACTIONS", [
  "row-select-and-centre",
] as const);

/**
 * The visual query builder's own keyboard-reachable actions — Phase 7 Stage 4, the third
 * keyboard-driven surface (`01_DOMAIN_MODEL.md` §8.1 / `06_DECISIONS.md` ADR-030's own analyst
 * -facing surface). `pin-node-from-search` and `second-root-needs-pinning-announced` are the two
 * actions proving ADR-030's own "explained at the point of drawing" standard end to end by
 * keyboard: pinning a second root is reachable without a mouse, and the live "needs pinning" cue
 * is announced to a screen reader the moment it appears, not only rendered visually. Canvas
 * pan/zoom/drag-to-place has no keyboard equivalent for the same disclosed reason `CANVAS_ACTIONS`
 * already gives its own pan/zoom/lasso — placing a node by keyboard goes through the ontology
 * palette's own list, not a drag gesture. Reaching the entity-type `Select`/search `Combobox` by
 * Tab is not itself listed — a native form control's own Tab-reachability is the browser's
 * guarantee, not this codebase's, the same exemption `MetricsPanel`'s own selects already
 * established; only what happens *after* a control is reached (a real state mutation, a real
 * network call) needs a case here.
 */
export const QUERY_BUILDER_ACTIONS = defineActionRegistry("QUERY_BUILDER_ACTIONS", [
  "palette-add-variable-node",
  "pin-node-from-search",
  "second-root-needs-pinning-announced",
  "delete-focused-pattern-element",
  "run-preview",
  "submit-run",
  "save-pattern",
  "load-saved-pattern",
] as const);

/**
 * Hotlists/monitors/the alert inbox — Phase 7 Stage 6c Part 2, the fourth keyboard-driven surface
 * (`keyboard/watch-panels-harness.tsx`'s own docstring has the reasoning for a separate
 * harness/spec pair). Every native `Input`/`Select`'s own Tab-reachability needs no case here, the
 * same exemption `QUERY_BUILDER_ACTIONS`'s own docstring already establishes — only an action with
 * real state mutation or a real network call does: creating a hotlist or a monitor, jumping from
 * an alert into a branched investigation, and opening that investigation once the jump result is
 * shown (a real callback out of the component, not only a local state flip).
 */
export const WATCH_PANEL_ACTIONS = defineActionRegistry("WATCH_PANEL_ACTIONS", [
  "submit-create-hotlist",
  "submit-create-monitor",
  "alert-row-jump",
  "jump-result-open-investigation",
] as const);

/**
 * The Judgements tab's own keyboard-reachable actions — Phase 8 Stage 4c, the fifth
 * keyboard-driven surface (`keyboard/assessment-panel-harness.tsx`'s own docstring has the
 * reasoning for a separate harness/spec pair, the same shape `WATCH_PANEL_ACTIONS` already
 * establishes for the fourth). Every native `Input`/`Select`'s own Tab-reachability needs no case
 * here — only an action with real state mutation or a real network call, or a real
 * canvas-touching effect, does: saving a judgement, a gap or an assumption; selecting a judgement
 * row to highlight its own evidence (`GlassCanvasHandle.highlightNodes`, a real effect on the
 * canvas, the same class of action `METRICS_PANEL_ACTIONS`'s own `row-select-and-centre` already
 * is for `focusOnNode`).
 */
export const ASSESSMENT_PANEL_ACTIONS = defineActionRegistry("ASSESSMENT_PANEL_ACTIONS", [
  "submit-save-judgement",
  "submit-save-gap",
  "submit-save-assumption",
  "judgement-row-select-highlights-evidence",
] as const);

/**
 * The export drawer's own keyboard-reachable actions — Phase 8 Stage 4e, the sixth
 * keyboard-driven surface (`keyboard/export-panel-harness.tsx`'s own docstring has the reasoning
 * for a separate harness/spec pair, the same shape `ASSESSMENT_PANEL_ACTIONS` already establishes
 * for the fifth). The artefact-kind `Select` needs no case here, the same native-control exemption
 * every other registry above already establishes — only a real network call does: submitting an
 * export that succeeds outright, and submitting one that is first blocked (`consult_originator`),
 * then re-submitted with both override fields filled.
 */
export const EXPORT_PANEL_ACTIONS = defineActionRegistry("EXPORT_PANEL_ACTIONS", [
  "submit-export-succeeds",
  "submit-export-after-override",
] as const);
