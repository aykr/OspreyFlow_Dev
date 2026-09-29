import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./design/tokens.css";
import "./design/primitives.css";
import { App } from "./App";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
