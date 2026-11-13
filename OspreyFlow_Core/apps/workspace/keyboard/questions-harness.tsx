// Questions keyboard harness (ADR-098 decision 4): the case's questions to the model, mounted on
// its own as the Questions drawer renders it. `questions.spec.ts` intercepts the routes at the
// transport; what the panel hands back (a change to the view, a document to open) is exposed on
// `window.__QUESTIONS__`. A chosen `[G-n]` is proved against the real canvas in `harness.html?questions=1`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { Drawer } from "../src/design/primitives/Drawer";
import { QuestionsPanel } from "../src/questions/QuestionsPanel";

declare global {
  interface Window {
    __QUESTIONS__?: {
      deltas: unknown[];
      opened: string | null;
      closed?: number;
      /** What the last question asked about, as the panel sent it. */
      scope?: unknown;
    };
  }
}

window.__QUESTIONS__ = {
  deltas: [],
  opened: null,
  closed: 0,
};

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// `?view=1`: the panel asking in a case view, as *Ask the model about these* opens it (ADR-144
// decision 4), until *Ask about the whole case instead*.
const inView = new URLSearchParams(window.location.search).get("view") === "1";

function Panel() {
  const [view, setView] = useState<{ id: string; name: string } | null>(
    inView ? { id: "v-q", name: "Questions on 2 items" } : null,
  );
  return (
    <QuestionsPanel
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="b1"
    onDelta={(delta) => window.__QUESTIONS__!.deltas.push(delta)}
    onOpenDocument={(id) => {
      window.__QUESTIONS__!.opened = id;
    }}
    selection={{ nodeIds: ["n-dana"], linkIds: [] }}
    view={view}
    onLeaveView={() => setView(null)}
    />
  );
}

createRoot(container).render(
  // Inside the Drawer, as `App.tsx` mounts it, so closing the drawer is provable here (rule 13).
  <Drawer open onClose={() => { window.__QUESTIONS__!.closed = (window.__QUESTIONS__!.closed ?? 0) + 1; }} title="Ask & Chat">
    <Panel />
  </Drawer>,
);
