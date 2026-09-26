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

// Every action on this surface that mutates state or reaches the network — each screen's own
// "Save", the Governance screen's exceptions-panel add/remove, and the Geospatial screen's three
// buttons (`build-basemap`/`verify` always refuse with a real 501, `harness/geospatial.py`'s own
// docstring has the reason, but the *keyboard reachability* of the button that triggers the call
// is proven the same way regardless of what the backend returns). Every native
// `<input>`/`<select>`/radio's own Tab-reachability needs no case here, the same exemption every
// registry in the shared module already establishes for a native control.
export const SETUP_SCREENS_ACTIONS = defineActionRegistry("SETUP_SCREENS_ACTIONS", [
  "submit-save-profile",
  "submit-save-components",
  "submit-save-models",
  "submit-save-governance",
  "submit-add-exception",
  "submit-remove-exception",
  "submit-register-provider",
  "submit-build-basemap",
  "submit-verify-map",
] as const);
