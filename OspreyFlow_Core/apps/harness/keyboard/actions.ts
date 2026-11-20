// `06_DECISIONS.md` ADR-049 Stage 2 §6 amendment 21: "a new keyboard-driven surface needs its own
// action registry and spec file, in the same change [as the first keyboard action]." Reuses
// `packages/glass-shared/src/keyboard/actionRegistry.ts`'s own mechanism directly (imported, not
// copied — the brief's own instruction): the registry lives in the shared package since PL4 slice C
// (ADR-152 decision 6), and this app is a second consumer of it, as `apps/workspace` is.
import { defineActionRegistry } from "@ospreyflow/glass-shared";

// Re-exported so this app's own `*.spec.ts` files import both the registry and its proving
// helpers from one local module, rather than reaching into the shared package twice per file.
export { assertAllCovered, registerCovered } from "@ospreyflow/glass-shared";

// Every action on this surface that mutates state or reaches the network — each screen's own
// "Save", the Governance screen's exceptions-panel add/remove, and the Geospatial screen's three
// buttons (`build-basemap`/`verify` run the Conduit's own code in its container, ADR-147;
// `harness/geospatial.py`'s own docstring has the reason), but the *keyboard reachability* of the button that triggers the call
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
  "submit-generate-artefacts",
  "download-artefact",
  "submit-confirm-artefacts",
  "submit-run-preflight",
  "submit-recheck",
  "submit-confirm-target",
  "submit-launch",
  // The guided install page's own screens (`ospreyflow install --gui`, ADR-114 Amendment 3, stage
  // B2c) — the same screens and the same registry, driven in `setup-screens.spec.ts` against
  // `harness/install_page.py`.
  "submit-save-mode",
  "submit-save-folders",
  "submit-save-demo-packs",
  "submit-save-cloud",
  "submit-save-domain",
  "submit-install",
  "submit-save-answers",
  // ADR-137 decision 3: a provider's key, entered on the install page's Models screen.
  "submit-set-key",
  // ADR-138 decision 1: a starter chosen on the Mode screen, and the GOV.UK service named.
  "submit-save-starter",
] as const);
