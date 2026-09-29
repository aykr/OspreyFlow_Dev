// The setup screens' own keyboard harness — renders the real `App`, wired to the real
// `/api/config` routes (this directory's own `playwright.config.ts` starts the real
// `harness.webapp` server as well as Vite, so nothing here is a stub of either).
import { createRoot } from "react-dom/client";

import { App } from "../src/App";
import "../../../apps/workspace/src/design/tokens.css";
import "../../workspace/src/design/primitives.css";
import "../src/app.css";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<App />);
