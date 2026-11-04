import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./design/fonts";
import "./design/tokens.css";
import "./design/primitives.css";
import { App } from "./App";
import { answerTheWindowThatAsked } from "./auth/callbackFrame";
import { deploymentAppearance, loadDeploymentSettings } from "./auth/oidcConfig";
import { applyBrand, brandFromUrl, loadBrandStylesheet } from "./brand/brand";
import { BrandFrame } from "./brand/BrandFrame";
import { applyTheme, readStoredTheme } from "./theme/theme";

// The saved light or dark choice is on the page before anything is drawn (ADR-070).
applyTheme(readStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// ADR-050 Amendment 1: the silent renewal's hidden iframe, or the sign-in-again window, brought back
// here by the identity provider only to carry its answer to the window that asked. Nothing is drawn.
const onlyCarryingAnAnswer = answerTheWindowThatAsked(window);

// Where the identity provider is, from the deployment itself (ADR-114 Amendment 4), before the
// sign-in machinery is built from it.
if (!onlyCarryingAnAnswer) void loadDeploymentSettings().then(async () => {
  // ADR-132: the deployment's brand, on the page before React draws anything, so no OspreyFlow chrome
  // is ever shown on a GOV.UK deployment. `?brand=` chooses one in a development build only.
  const appearance = deploymentAppearance();
  const brand = brandFromUrl(window.location.search, import.meta.env.DEV) ?? appearance.brand;
  applyBrand(brand);
  applyTheme(readStoredTheme());
  // The GOV.UK stylesheet, awaited so the header is never drawn unstyled; never fetched otherwise.
  await loadBrandStylesheet(brand);
  createRoot(container).render(
    <StrictMode>
      {/* The frame also sets the page title, "<service> – GOV.UK" under GOV.UK (ADR-132 Am. 5). */}
      <BrandFrame appearance={{ ...appearance, brand }}>
        <App />
      </BrandFrame>
    </StrictMode>,
  );
});
