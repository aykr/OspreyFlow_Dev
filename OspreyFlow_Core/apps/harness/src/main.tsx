import { createRoot } from "react-dom/client";

import "../../../apps/workspace/src/design/tokens.css";
import "../../workspace/src/design/primitives.css";
import "./app.css";
import { applyTheme, readStoredTheme } from "../../workspace/src/theme/theme";
import { App } from "./App";

// The light or dark choice made on any page of this host is on this one before anything is drawn (ADR-072).
applyTheme(readStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<App />);
