import { createRoot } from "react-dom/client";

import "../../../apps/workspace/src/design/tokens.css";
import "../../workspace/src/design/primitives.css";
import "./app.css";
import { applyTheme, readStoredTheme } from "../../workspace/src/theme/theme";
import { App } from "./App";
import { InstallApp } from "./InstallApp";

// The light or dark choice made on any page of this host is on this one before anything is drawn (ADR-072).
applyTheme(readStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// The same bundle serves two pages. Only `harness/install_page.py` answers this route (behind its
// token cookie); the Set-up console's own server has no such route, so it gets the Set-up console.
fetch("/api/install/state", { credentials: "same-origin" })
  .then((reply) => reply.ok)
  .catch(() => false)
  .then((guided) => {
    createRoot(container).render(guided ? <InstallApp /> : <App />);
  });
