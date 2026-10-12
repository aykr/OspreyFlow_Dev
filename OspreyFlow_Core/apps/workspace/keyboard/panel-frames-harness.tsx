// The side panel and timeline frames (`src/layout/PanelFrames.tsx`) laid out as `App.tsx` lays them
// out: a work area with a stand-in for the canvas and the side panel beside it, the timeline below.
// The side panel holds three stand-in panels in a `SidePanelStack` (ADR-085); the first is a text
// box, to show that what is typed in it survives hiding the panel.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { BottomPanelFrame, DetailsToggle, SidePanelFrame } from "../src/layout/PanelFrames";
import { SidePanelStack } from "../src/layout/SidePanelStack";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--surface-base, #111)" }}>
    <div id="work-area" style={{ flex: 1, display: "flex", minHeight: 0, position: "relative" }}>
      <div id="canvas-stand-in" style={{ flex: 1, position: "relative" }}>
        {/* In the Glass, Details is in the canvas's own toolbar (ADR-115 E4). */}
        <DetailsToggle />
      </div>
      <SidePanelFrame name="Inspector">
        <SidePanelStack
          panels={[
            { id: "inspector", name: "Inspector", content: <textarea aria-label="Query" rows={4} /> },
            { id: "metrics", name: "Metrics", content: <div>Metrics</div> },
            { id: "query-builder", name: "Query builder", content: <div>Query builder</div> },
          ]}
        />
      </SidePanelFrame>
    </div>
    <BottomPanelFrame title="Timeline" height={252}>
      <div id="timeline-body" style={{ height: "100%" }}>
        Timeline
      </div>
    </BottomPanelFrame>
  </div>,
);
