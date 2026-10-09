// Explore keyboard harness (ADR-100): where to start in a case's data, inside the `Drawer` the Glass
// opens it in (8 October 2026: mounted on its own page, the panel scrolled with the page, so no case
// saw the deployed drawer cut it off at the window's height). `explore.spec.ts` intercepts the routes at the
// transport; the node each pick would put on the canvas is exposed on `window.__EXPLORE__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { Drawer } from "../src/design/primitives/Drawer";
import { ExplorePanel } from "../src/explore/ExplorePanel";

declare global {
  interface Window {
    __EXPLORE__?: {
      picked: string[];
      links: string[];
      days: string[];
      deltas: number[];
      /** ADR-100 Amendment 9: [node id, how many links came] per budget add. */
      budget: [string, number][];
      expandedAll: string[];
    };
  }
}

window.__EXPLORE__ = { picked: [], links: [], days: [], deltas: [], budget: [], expandedAll: [] };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <Drawer open onClose={() => undefined} title="Explore">
  <ExplorePanel
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="c1"
    edgeTypes={[]}
    onPick={(node) => window.__EXPLORE__!.picked.push(node.id)}
    onPickLink={(link) => window.__EXPLORE__!.links.push(link.edge.id)}
    onPickDay={(day) => window.__EXPLORE__!.days.push(day.start)}
    onApplyDelta={(delta) => window.__EXPLORE__!.deltas.push(delta.seq)}
    onAddLinks={(node, links) => window.__EXPLORE__!.budget.push([node.id, links.length])}
    onExpandAll={(node) => window.__EXPLORE__!.expandedAll.push(node.id)}
  />
  </Drawer>,
);
