import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./design/tokens.css";
import "./design/primitives.css";
import { App } from "./App";
import { applyTheme, readStoredTheme } from "./theme/theme";

// The saved light or dark choice is on the page before anything is drawn (ADR-070).
applyTheme(readStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
