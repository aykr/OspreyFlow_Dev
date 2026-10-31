import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./design/fonts";
import "./design/tokens.css";
import "./design/primitives.css";
import { App } from "./App";
import { deploymentAppearance, loadDeploymentSettings } from "./auth/oidcConfig";
import { applyBrand, brandFromUrl, brandTitle } from "./brand/brand";
import { applyTheme, readStoredTheme } from "./theme/theme";

// The saved light or dark choice is on the page before anything is drawn (ADR-070).
applyTheme(readStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// Where the identity provider is, from the deployment itself (ADR-114 Amendment 4), before the
// sign-in machinery is built from it.
void loadDeploymentSettings().then(() => {
  // ADR-132: the deployment's brand, on the page before React draws anything, so no OspreyFlow chrome
  // is ever shown on a GOV.UK deployment. `?brand=` chooses one in a development build only.
  const appearance = deploymentAppearance();
  const brand = brandFromUrl(window.location.search, import.meta.env.DEV) ?? appearance.brand;
  applyBrand(brand);
  applyTheme(readStoredTheme());
  document.title = brandTitle(appearance, brand, document.title);
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
