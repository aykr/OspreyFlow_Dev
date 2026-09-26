// `06_DECISIONS.md` ADR-049 Stage 2 §6 amendment 21: "a new keyboard-driven surface needs its own
// action registry and spec file, in the same change [as the first keyboard action]." Reuses
// `apps/workspace/keyboard/actionRegistry.ts`'s own mechanism directly (imported, not copied —
// the brief's own instruction) rather than moving it to a shared package: this app is a second
// consumer of one already-shared module, not a reason to relocate it and touch every existing
// import in `apps/workspace` to do so.
import { defineActionRegistry } from "../../workspace/keyboard/actionRegistry";

// Re-exported so this app's own `*.spec.ts` files import both the registry and its proving
// helpers from one local module, rather than reaching into `apps/workspace` twice per file.
export { assertAllCovered, registerCovered } from "../../workspace/keyboard/actionRegistry";

// The three screens' own "Save" actions — each a real `PUT /api/config` call, the only actions on
// this surface that mutate state or reach the network. Every native `<input>`/`<select>`/radio's
// own Tab-reachability needs no case here, the same exemption every registry in the shared module
// already establishes for a native control.
export const SETUP_SCREENS_ACTIONS = defineActionRegistry("SETUP_SCREENS_ACTIONS", [
  "submit-save-profile",
  "submit-save-components",
  "submit-save-models",
] as const);
