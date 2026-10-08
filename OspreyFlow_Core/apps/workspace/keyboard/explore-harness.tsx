// Explore keyboard harness (ADR-100): where to start in a case's data, mounted on its own as the
// Explore drawer and the empty canvas render it. `explore.spec.ts` intercepts the routes at the
// transport; the node each pick would put on the canvas is exposed on `window.__EXPLORE__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { ExplorePanel } from "../src/explore/ExplorePanel";

declare global {
  interface Window {
    __EXPLORE__?: { picked: string[] };
  }
}

window.__EXPLORE__ = { picked: [] };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <ExplorePanel
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="c1"
    edgeTypes={[]}
    onPick={(node) => window.__EXPLORE__!.picked.push(node.id)}
  />,
);
