// Find connections (ADR-116) on its own: `connections.spec.ts` intercepts the case's suggest,
// connections and seed routes and walks the panel by keyboard. A node counts as selected on the canvas
// when the spec says so (`__CONNECTIONS__.select`); what the panel hands back is recorded.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import type { Node } from "../../../packages/schemas/generated";
import { FindConnectionsPanel } from "../src/connections/FindConnectionsPanel";

declare global {
  interface Window {
    __CONNECTIONS__?: {
      deltas: unknown[];
      marks: [string, number][];
      cleared: number;
      select: (node: Node | null) => void;
    };
  }
}

const recorded = { deltas: [] as unknown[], marks: [] as [string, number][], cleared: 0 };

function Harness() {
  const [selected, setSelected] = useState<Node | null>(null);
  window.__CONNECTIONS__ = { ...recorded, select: setSelected };
  return (
    <FindConnectionsPanel
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      investigationId="inv-1"
      selected={selected}
      canvas={{ hasNode: () => false, hasEdge: () => false }}
      onDelta={(delta) => {
        recorded.deltas.push(delta);
        window.__CONNECTIONS__!.deltas = recorded.deltas;
      }}
      onMark={(marks) => {
        recorded.marks.push(...marks);
        window.__CONNECTIONS__!.marks = recorded.marks;
      }}
      onClearMarks={() => {
        recorded.cleared += 1;
        window.__CONNECTIONS__!.cleared = recorded.cleared;
      }}
    />
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);
