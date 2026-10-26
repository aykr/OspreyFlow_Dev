// Questions keyboard harness (ADR-098 decision 4): the case's questions to the model, mounted on
// its own as the Questions drawer renders it. `questions.spec.ts` intercepts the routes at the
// transport; what the panel hands back (a change to the view, a document to open) is exposed on
// `window.__QUESTIONS__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { Drawer } from "../src/design/primitives/Drawer";
import { bringFactIntoView, type FactCanvas } from "../src/questions/graphFacts";
import { QuestionsPanel } from "../src/questions/QuestionsPanel";

declare global {
  interface Window {
    __QUESTIONS__?: {
      deltas: unknown[];
      opened: string | null;
      closed?: number;
      /** What the canvas was told by a chosen `[G-n]`: the same `bringFactIntoView` `App.tsx` calls,
       * against a canvas that records. */
      canvas: { selectedLink: string | null; selectedNodes: string[]; centred: string | null };
      /** What the last question asked about, as the panel sent it. */
      scope?: unknown;
    };
  }
}

window.__QUESTIONS__ = {
  deltas: [],
  opened: null,
  closed: 0,
  canvas: { selectedLink: null, selectedNodes: [], centred: null },
};

const canvas: FactCanvas = {
  highlightNodes: (ids) => {
    window.__QUESTIONS__!.canvas.selectedNodes = [...ids];
    window.__QUESTIONS__!.canvas.selectedLink = null;
  },
  selectLink: (id) => {
    window.__QUESTIONS__!.canvas.selectedLink = id;
    window.__QUESTIONS__!.canvas.selectedNodes = [];
  },
  centreOn: (id) => {
    window.__QUESTIONS__!.canvas.centred = id;
  },
};

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  // Inside the Drawer, as `App.tsx` mounts it, so closing the drawer is provable here (rule 13).
  <Drawer open onClose={() => { window.__QUESTIONS__!.closed = (window.__QUESTIONS__!.closed ?? 0) + 1; }} title="Questions">
    <QuestionsPanel
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="b1"
    onDelta={(delta) => window.__QUESTIONS__!.deltas.push(delta)}
    onOpenDocument={(id) => {
      window.__QUESTIONS__!.opened = id;
    }}
    selection={{ nodeIds: ["n-dana"], linkIds: [] }}
    onSelectFacts={(citation) => bringFactIntoView(canvas, citation)}
    />
  </Drawer>,
);
