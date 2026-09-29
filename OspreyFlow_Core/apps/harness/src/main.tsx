import { createRoot } from "react-dom/client";

import "../../../apps/workspace/src/design/tokens.css";
import "../../workspace/src/design/primitives.css";
import "./app.css";
import { App } from "./App";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<App />);
