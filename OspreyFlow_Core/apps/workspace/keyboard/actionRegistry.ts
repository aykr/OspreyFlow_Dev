/**
 * This registry's own resolution of a disclosed gap on
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
 * **`defineActionRegistry` self-registers into `ALL_REGISTRIES`** so `registryCoverage.test.ts`
 * (a Vitest test, not a Playwright spec — see its own header) can enumerate every declared
 * registry by statically importing this module, and fail when one has no `assertAllCovered` call
 * reaching it anywhere under `apps/workspace/keyboard/*.spec.ts` — the gap a purely runtime check
 * cannot close, since nothing forces a *test* asserting a registry's own coverage to exist merely
 * because the registry itself does.
 *
 * This paragraph named `check-registry-coverage.mjs`, "a plain Node script", until 25 September
 * 2026. **No such file has ever existed** — the mechanism it describes is real and is the Vitest
 * test above. Corrected rather than left, because a citation to a file that is not there reads as
 * a guarantee and is the exact failure `CLAUDE.md` rule 12 names. It is the second such citation
 * found the same day; `apps/workspace/Dockerfile` carried the other.
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
  "zoom-in-and-out-by-keyboard",
  "fit-to-view-by-keyboard",
  "legend-folds-by-keyboard",
  "show-previous-positions-by-keyboard",
  "grid-toggles-by-keyboard",
  "show-links-among-all-by-keyboard",
  "move-the-selection-with-shift-and-arrows",
  "focus-establishes-ring",
  "tab-leaves-the-canvas",
  "ctrl-arrow-cycles-ring",
  // Round 12d: `Ctrl`/`Cmd`+`Shift`+Arrow walks *every* node in the working set, adjacency or
  // not. Distinct from `ctrl-arrow-cycles-ring` (which cycles the selection) and from
  // `arrow-walk-forward`/`backward` (which follow edges): without it there was no keyboard route
  // to a two-node selection over two non-adjacent nodes, so `menu-item-explain-cluster` and
  // `menu-item-find-paths` — both gated on `selected.size === 2` — were mouse-only in practice
  // while this registry recorded them as covered. `CLAUDE.md` rule 13.
  "ctrl-shift-arrow-walks-every-node",
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
  // Owner ruling R7 (TENTATIVE, 27 September 2026) — step one of two-step retraction. Offered on
  // every node, so it is the *last* item in the list on any node and the keyboard walkthrough
  // reaches it by `End` rather than by counting Tabs, which would otherwise have to change every
  // time an edge type is added to the fixture.
  "menu-item-mark-for-suppression",
  // ADR-105 Amendment 1: Set picture… on an entity a picture may depict, handing over to the
  // Inspector's Picture part.
  "menu-item-set-picture",
  "overlay-dismiss-cluster-explain",
  // The pathfinder — the keyboard-walkthrough's own entry drew
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
  // 3 October 2026 (ADR-062, ADR-063, ADR-060 Amendment 1, ADR-064): the view can be tidied and a
  // link can be selected. Each was added without a keyboard route proven until the keyboard suite
  // was run against it, which is what these entries and their test cases close.
  "delete-removes-selected-nodes",
  "clear-view-by-keyboard",
  // 4 October 2026 (ADR-084): the selected nodes can be sent to a new tab. A button in the same
  // row as Remove selected and Clear view, so it is reached by Tab like them.
  "branch-selected-opens-a-new-tab",
  "branch-selected-from-a-selected-nodes-menu",
  "layout-menu-chooses-layout",
  "layout-menu-chooses-force-directed-tree",
  "layout-menu-chooses-clustered-bubbles-and-what-they-group-by",
  "l-steps-through-the-focused-nodes-links",
  "delete-hides-selected-link",
  "show-hidden-links-by-keyboard",
  "overlay-dismiss-large-expansion",
  // ADR-077: an expansion that adds nothing says so, and the message is dismissed by Escape.
  "expand-with-nothing-new-says-so",
  // ADR-079: the Icons control is reached by Tab and a drawing chosen with the arrow keys, and a
  // picture can be given from a file.
  "icons-menu-by-keyboard",
  "icon-picture-from-file",
  "large-expansion-add-all-by-keyboard",
  // 3 October 2026 (ADR-066): Communities groups the nodes in view and folds a group into one node.
  // Every way of doing it with the mouse has a keyboard route, each proved by its own case.
  "communities-button-by-keyboard",
  "g-folds-and-opens-the-focused-nodes-group",
  "box-fold-button-by-keyboard",
  "collapse-all-and-expand-all-by-keyboard",
  // 3 October 2026 (ADR-076): the analyst chooses which property names each type of node. The button
  // and the pickers it opens are native controls, but whether Tab reaches them, an arrow key chooses,
  // and the label on the canvas then changes is exactly what the suite exists to prove.
  "labels-menu-by-keyboard",
  "an-expansion-leaves-the-view-and-the-settled-nodes-where-they-were",
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
  "ranking-opens-loaded-and-folds-by-keyboard",
  "row-select-and-centre",
  "filter-section-sets-a-strength-floor-by-keyboard",
  "filter-section-dims-below-a-metric-value-by-keyboard",
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
  // ADR-096: the panel's parts fold; a folded one opens by Enter on its header.
  "open-a-folded-part-by-keyboard",
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
 *
 * `export-produces-a-downloadable-artefact` — Phase 8 Stage 4h: a successful submit now also
 * triggers a real file download (`ExportPanel.tsx`'s own `downloadArtefact`); proven via the
 * subgraph shape (fully real in the harness, no fake renderer needed, unlike chart) by observing
 * Playwright's own `page.waitForEvent("download")` fire with the artefact's own filename.
 */
export const EXPORT_PANEL_ACTIONS = defineActionRegistry("EXPORT_PANEL_ACTIONS", [
  "submit-export-succeeds",
  "submit-export-after-override",
  "export-produces-a-downloadable-artefact",
] as const);

/**
 * The timeline's own playback and cross-case-overlay controls — Phase 8 Stage 4f, the seventh
 * keyboard-driven surface (`keyboard/timeline-playback-harness.tsx`'s own docstring has the
 * reasoning for a separate harness/spec pair, the same shape every registry above already
 * establishes). The speed `Select` and the cross-case-scope `Input` need no case here of their
 * own, the same native-control exemption every other registry above already establishes — only an
 * action with a real timed effect or a real network call does: pressing Play actually advances the
 * playback clock forward (proven by observing the reported fraction change, not just that the
 * button's own `aria-pressed` flips), and entering a second investigation's own id triggers the
 * real cross-case histogram fetch and renders the second track.
 */
export const TIMELINE_PLAYBACK_ACTIONS = defineActionRegistry("TIMELINE_PLAYBACK_ACTIONS", [
  "timeline-mode-switch-by-keyboard",
  "toggle-playback-advances-the-clock",
  "set-exact-dates-reveals-the-date-boxes",
  "overlay-another-case-reveals-its-box",
  "cross-case-overlay-loads-second-track",
  "no-dated-events-says-so-and-offers-no-brush-or-playback",
] as const);

/**
 * The sign-in screen's own keyboard-reachable action — `06_DECISIONS.md` ADR-050, the eighth
 * keyboard-driven surface (`keyboard/sign-in-harness.tsx`'s own docstring has the reasoning for a
 * separate harness/spec pair, the same shape every registry above already establishes). One action,
 * not the native button's own Tab-reachability (free, the browser's guarantee, the same exemption
 * every other registry already draws): activating "Sign in" triggers a real `oidc-client-ts`
 * `signinRedirect()` — a real OIDC discovery fetch followed by a real top-level navigation to the
 * identity provider's authorization endpoint with the right `client_id`/`response_type`/PKCE
 * challenge, not a mocked callback.
 */
export const SIGN_IN_ACTIONS = defineActionRegistry("SIGN_IN_ACTIONS", [
  "submit-sign-in",
] as const);

/**
 * The Inspector's Notes section for a selected link (ADR-075) — a keyboard-driven surface of its
 * own (`keyboard/link-notes-harness.tsx`). Each action changes stored state through a real network
 * call, so each needs a case; a native textarea's own Tab-reachability does not (the exemption the
 * registries above already state). Entries are the ways a note is written, changed or dropped
 * without a mouse, including the two that must not change anything.
 */
export const LINK_NOTES_ACTIONS = defineActionRegistry("LINK_NOTES_ACTIONS", [
  "ctrl-enter-adds-a-note",
  "add-note-button-by-keyboard",
  "edit-own-note-and-save-by-keyboard",
  "escape-cancels-an-edit-and-returns-focus",
  "delete-own-note-by-keyboard-after-confirming",
  "cancel-a-delete-by-keyboard",
] as const);

/**
 * The right-click menu on a link (ADR-080), reached without a mouse: `L` selects a focused node's
 * link and `\` opens the menu for it (`keyboard/link-menu.spec.ts`, on the `?fixture=same-as`
 * harness). Each entry either changes the view or writes with the analyst's name and a reason, so
 * each needs a case that activates it; the two ways a reason is *not* accepted are cases too.
 */
export const LINK_MENU_ACTIONS = defineActionRegistry("LINK_MENU_ACTIONS", [
  "backslash-opens-the-menu-of-a-selected-same-as-link",
  "collapse-folds-the-matched-nodes-into-one",
  "group-node-menu-expands-the-group",
  "confirm-asks-why-and-sends-the-reason",
  "mark-not-same-asks-why-and-sends-the-reason",
  "reason-is-required-before-confirming",
  "escape-cancels-the-reason-box-and-sends-nothing",
  "explain-this-link-shows-the-cluster",
  "hide-link-from-the-menu",
  "add-a-note-hands-over-to-the-inspector",
  "other-links-offer-change-and-history-and-hand-over",
  "moving-the-resolution-slider-opens-a-same-as-fold",
  "show-events-hands-over-to-the-inspector",
  "show-emails-puts-the-windows-emails-on-the-canvas-as-documents",
  "put-the-emails-on-the-canvas-from-the-link-menu",
] as const);

/**
 * The Inspector's *Change this link* form (ADR-080) — a keyboard-driven surface of its own
 * (`keyboard/link-change-harness.tsx`). Saving writes through a real network call with a required
 * reason, so each way in, the save, the refusal without a reason and the cancel each need a case.
 */
/** The Inspector's Emails section (ADR-089): the events behind a link, paged, one opened to read. */
export const LINK_EVENTS_ACTIONS = defineActionRegistry("LINK_EVENTS_ACTIONS", [
  "events-list-newest-first-and-show-more-by-keyboard",
  "enter-on-an-email-opens-it-and-back-returns",
  "extract-entities-by-keyboard-lists-the-findings",
  "accept-a-finding-by-keyboard",
  "read-full-screen-from-an-opened-email",
  // ADR-095 decision 4: the list puts the emails on the canvas, as the link menu does.
  "put-the-emails-on-the-canvas-from-the-list",
  // ADR-098: the model on request, and a finding rejected.
  "ask-the-model-to-extract-by-keyboard",
  "reject-a-finding-by-keyboard",
] as const);

/** The selection made easy to see and work with (ADR-093): the canvas chip and the Inspector's list.
 * `keyboard/selection.spec.ts`. */
export const SELECTION_ACTIONS = defineActionRegistry("SELECTION_ACTIONS", [
  // ADR-097 step 1: the selection bar replaces the corner chip.
  "clear-the-selection-from-the-selection-bar",
  "remove-the-selection-from-the-selection-bar",
  "expand-the-selection-from-the-selection-bar",
  "centre-on-a-selected-node-from-the-list",
  "remove-a-node-from-the-selection-from-the-list",
  // ADR-098 decision 1.
  "show-links-among-the-selection-from-the-selection-bar",
  // ADR-098 decision 4.
  "ask-the-model-about-the-selected-documents-from-the-selection-bar",
] as const);

/** What a case reads (ADR-099): ticked when the case is made, changed by its Author.
 * `keyboard/case-datasets.spec.ts`. */
export const CASE_DATASETS_ACTIONS = defineActionRegistry("CASE_DATASETS_ACTIONS", [
  "tick-datasets-and-create-a-case-by-keyboard",
  "change-what-a-case-reads-by-keyboard",
] as const);

/** Who can open a case (ADR-052 §9): its Author gives and removes levels. `keyboard/case-access.spec.ts`. */
export const CASE_ACCESS_ACTIONS = defineActionRegistry("CASE_ACCESS_ACTIONS", [
  "give-an-account-access-by-keyboard",
  "remove-an-accounts-access-by-keyboard",
] as const);

/** Where to start in a case's data (ADR-100): a node from the most connected, or from a type's
 * most connected, put on the canvas; a ranking paged. `keyboard/explore.spec.ts`. */
export const EXPLORE_ACTIONS = defineActionRegistry("EXPLORE_ACTIONS", [
  "put-a-most-connected-node-on-the-canvas-by-keyboard",
  "open-an-entity-type-and-put-one-on-the-canvas-by-keyboard",
  "show-more-of-a-ranking-by-keyboard",
  // ADR-100 decision 5.
  "put-a-busiest-link-on-the-canvas-by-keyboard",
  "set-the-timeline-to-a-busiest-day-by-keyboard",
  // ADR-100 decision 6.
  "put-a-groups-centre-on-the-canvas-by-keyboard",
  "put-a-bridge-on-the-canvas-by-keyboard",
  // ADR-100 decision 7 (Amendment 6).
  "put-a-confirmed-node-on-the-canvas-by-keyboard",
  "put-a-marked-node-on-the-canvas-by-keyboard",
  // ADR-100 decision 8 (Amendment 7).
  "run-a-starter-question-by-keyboard",
  // ADR-100 Amendment 9: the link budget on a ranked node.
  "add-a-node-with-its-busiest-links-by-keyboard",
  "add-a-node-with-all-its-links-by-keyboard",
] as const);

/** The case's questions to the model (ADR-098 decision 4): asked, answered with what it draws on,
 * and its proposals accepted or rejected. `keyboard/questions.spec.ts`. */
/** The pipeline canvas, read-only (ADR-108 phase A): every node reachable and its settings
 * readable, by keyboard alone. Phase B's editable canvas extends this registry. */
export const PIPELINE_CANVAS_ACTIONS = defineActionRegistry("PIPELINE_CANVAS_ACTIONS", [
  "walk-the-pipeline-nodes-by-keyboard",
  "read-a-nodes-settings-by-keyboard",
] as const);

/** The pipeline Studio (ADR-108 phase B): the fresh screens, every action keyboard-provable. */
export const PIPELINE_STUDIO_ACTIONS = defineActionRegistry("PIPELINE_STUDIO_ACTIONS", [
  "create-a-pipeline-by-keyboard",
  "open-a-pipeline-by-keyboard",
  "add-a-source-branch-by-keyboard",
  "choose-a-domain-pack-by-keyboard",
  "apply-extract-settings-by-keyboard",
  "remove-a-node-by-keyboard",
  "open-the-map-editor-by-keyboard",
  // ADR-108, 10 October 2026: the Connect gate rehosted under the first source node.
  "open-the-source-settings-by-keyboard",
] as const);

/** The Alerts place (ADR-109 phase B): the case team's queue, an alert's explanation and its
 * triage, the rules (an Author deploys and retires), held rows and the rule audit, every action by
 * keyboard alone. `keyboard/alerts.spec.ts`. */
export const ALERTS_ACTIONS = defineActionRegistry("ALERTS_ACTIONS", [
  "open-an-alert-from-the-queue-by-keyboard",
  "claim-an-alert-by-keyboard",
  "release-an-alert-by-keyboard",
  "show-an-alert-on-the-canvas-by-keyboard",
  "close-an-alert-with-a-reason-by-keyboard",
  "filter-the-queue-by-keyboard",
  "deploy-a-rule-by-keyboard",
  "retire-a-rule-by-keyboard",
  "release-held-rows-by-keyboard",
  "reject-held-rows-by-keyboard",
  "page-the-rule-audit-by-keyboard",
  // ADR-109 phase F: a KYC rule, with its switches.
  "deploy-a-kyc-rule-by-keyboard",
  // ADR-109 phase D: the no-code typology builder — a drawn, saved pattern deployed as a rule.
  "deploy-a-drawn-pattern-rule-by-keyboard",
] as const);

/** The Ownership place (ADR-109 phase C): find an entity, trace its beneficial owners, change the
 * threshold, read a party's chains, put the structure on the canvas. `keyboard/ownership.spec.ts`. */
export const OWNERSHIP_ACTIONS = defineActionRegistry("OWNERSHIP_ACTIONS", [
  "find-an-entity-and-trace-its-ownership-by-keyboard",
  "trace-again-at-another-threshold-by-keyboard",
  "read-a-partys-chains-by-keyboard",
  "show-the-structure-on-the-canvas-by-keyboard",
  // ADR-109 phase F: the customer's KYC status and baseline risk.
  "read-a-customers-due-diligence-by-keyboard",
] as const);

export const QUESTIONS_ACTIONS = defineActionRegistry("QUESTIONS_ACTIONS", [
  "ask-a-question-with-ctrl-enter",
  "ask-a-question-with-the-ask-button",
  "open-a-cited-document-by-keyboard",
  "accept-a-proposal-by-keyboard",
  "reject-a-proposal-by-keyboard",
  // The drawer's visible Close (the owner, 9 October 2026).
  "close-the-questions-drawer-by-keyboard",
] as const);

/** Files added straight to a case (ADR-094 step 3): from the strip over the canvas, standing alone,
 * or from a node's menu, held by it. `keyboard/add-files.spec.ts`. */
export const ADD_FILES_ACTIONS = defineActionRegistry("ADD_FILES_ACTIONS", [
  "add-files-to-the-case-from-the-strip",
  "add-files-held-by-a-node-from-its-menu",
] as const);

/** The full-screen reader (ADR-092): opened from a Document on the canvas, read, extracted from,
 * closed. `keyboard/reader.spec.ts`. */
export const READER_ACTIONS = defineActionRegistry("READER_ACTIONS", [
  "enter-on-a-document-opens-it-to-read",
  "escape-closes-the-reader",
  "extract-and-accept-from-the-reader-by-keyboard",
  // The owner's ask, 6 October 2026: a Document's right-click menu opens it full screen.
  "read-full-screen-from-a-documents-menu",
  // The owner's ask, 6 October 2026: a Reject beside each Accept.
  "reject-a-finding-in-the-reader-by-keyboard",
  // ADR-108 ruling Q1: the pending findings, enumerated, accepted as one decision.
  "accept-all-pending-in-the-reader-by-keyboard",
  // ADR-098 decision 5: an entity marked by hand.
  "mark-an-entity-in-the-reader-by-keyboard",
  // ADR-098 decision 3: the language model on request.
  "ask-the-model-to-extract-in-the-reader-by-keyboard",
] as const);

/** The administrator's *Proposed types* list (ADR-090 C3): opened from the top bar, each proposal
 * promoted (with its basis, and a new ID when its name is taken), rejected, or retired.
 * `keyboard/proposed-types.spec.ts`. */
export const PROPOSED_TYPES_ACTIONS = defineActionRegistry("PROPOSED_TYPES_ACTIONS", [
  "open-the-list-from-the-top-bar-and-escape-closes-it",
  "promote-by-keyboard-choosing-the-basis",
  "rename-at-promotion-by-keyboard",
  "reject-by-keyboard",
  "retire-by-keyboard",
] as const);

/** The Inspector's parts (ADR-096): each folds under its header, opening *Change this link* lands in
 * the form, and a link-menu hand-over opens its part. `keyboard/inspector.spec.ts`. */
export const INSPECTOR_ACTIONS = defineActionRegistry("INSPECTOR_ACTIONS", [
  "a-part-opens-and-folds-by-keyboard",
  "opening-change-this-link-opens-the-form",
  "a-menu-hand-over-opens-its-part",
  // ADR-100 Amendment 7 decision 4.
  "ask-who-shares-contacts-and-add-a-pair-by-keyboard",
  // ADR-102 decision 4.
  "lower-a-links-handling-with-a-confirmation-by-keyboard",
  // ADR-105 decision 6.
  "set-an-entitys-own-picture-by-keyboard",
  "remove-an-entitys-own-picture-by-keyboard",
  // ADR-109 phase E: the selected entity's neighbourhood risk, asked on demand.
  "score-a-neighbourhoods-risk-by-keyboard",
] as const);

/** The workspace shell (ADR-097 step 1): the top bar, the left rail, the classification strip.
 * `keyboard/shell.spec.ts`. */
export const SHELL_ACTIONS = defineActionRegistry("SHELL_ACTIONS", [
  "slash-moves-focus-to-search",
  "rail-entries-by-keyboard",
  "rail-shows-and-hides-names-by-keyboard",
  // ADR-111: the view switch, Reports included — never proved by keyboard before it.
  "views-chosen-by-keyboard",
] as const);

export const ADMIN_ACTIONS = defineActionRegistry("ADMIN_ACTIONS", [
  "save-a-persons-roles-by-keyboard",
  "register-a-dashboard-by-keyboard",
  "remove-a-dashboard-by-keyboard",
  "ask-the-system-again-by-keyboard",
] as const);

export const REPORTS_ACTIONS = defineActionRegistry("REPORTS_ACTIONS", [
  "change-the-reports-period-by-keyboard",
  "download-the-figures-by-keyboard",
] as const);

export const LINK_CHANGE_ACTIONS = defineActionRegistry("LINK_CHANGE_ACTIONS", [
  "enter-on-change-this-link-opens-the-form-at-the-type",
  "change-the-type-and-save-with-ctrl-enter",
  "save-needs-a-reason",
  "escape-closes-the-form-and-changes-nothing",
  "opened-by-the-link-menu-lands-on-the-type",
  "choose-what-stands-behind-the-link-before-saving",
  // ADR-090 C2: *Define a new type…*, proposed by keyboard and chosen in the form.
  "define-a-new-type-by-keyboard-and-it-is-chosen",
] as const);

/**
 * The frames round the Glass's side panel and timeline (`src/layout/PanelFrames.tsx`): hide each,
 * and open the side panel to the whole work area so the query builder has room. Each is a button, so
 * each needs a case proving it by keyboard alone (`keyboard/panel-frames.spec.ts`).
 */
export const PANEL_FRAME_ACTIONS = defineActionRegistry("PANEL_FRAME_ACTIONS", [
  "hide-and-show-the-side-panel-by-keyboard",
  "open-the-side-panel-to-the-full-width-and-return-by-keyboard",
  "hide-and-show-the-timeline-by-keyboard",
  "move-a-side-panel-up-and-down-by-keyboard",
  "move-a-side-panel-with-alt-arrows-by-keyboard",
  "fold-a-side-panel-by-keyboard",
  "resize-the-side-panel-by-keyboard",
  "resize-a-stacked-panel-by-keyboard",
  "resize-the-timeline-by-keyboard",
] as const);
