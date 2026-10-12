import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./design/tokens.css";
import "./design/primitives.css";
import { App } from "./App";
import { loadDeploymentSettings } from "./auth/oidcConfig";
import { applyTheme, readStoredTheme } from "./theme/theme";

// The saved light or dark choice is on the page before anything is drawn (ADR-070).
applyTheme(readStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// Where the identity provider is, from the deployment itself (ADR-114 Amendment 4), before the
// sign-in machinery is built from it.
void loadDeploymentSettings().then(() => {
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
