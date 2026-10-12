// The guided install page's own keyboard harness — renders the real `InstallApp`, wired to the real
// `harness/install_page.py` (this directory's own `playwright.config.ts` starts it behind its token
// and with a stub in place of the real install, so nothing here is a stub of the page itself).
import { createRoot } from "react-dom/client";

import { InstallApp } from "../src/InstallApp";
import { applyTheme, readStoredTheme } from "../../workspace/src/theme/theme";
import "../../../apps/workspace/src/design/tokens.css";
import "../../workspace/src/design/primitives.css";
import "../src/app.css";

applyTheme(readStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<InstallApp />);
