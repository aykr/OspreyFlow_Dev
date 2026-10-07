// Questions keyboard harness (ADR-098 decision 4): the case's questions to the model, mounted on
// its own as the Questions drawer renders it. `questions.spec.ts` intercepts the routes at the
// transport; what the panel hands back (a change to the view, a document to open) is exposed on
// `window.__QUESTIONS__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { QuestionsPanel } from "../src/questions/QuestionsPanel";

declare global {
  interface Window {
    __QUESTIONS__?: { deltas: unknown[]; opened: string | null };
  }
}

window.__QUESTIONS__ = { deltas: [], opened: null };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <QuestionsPanel
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="b1"
    onDelta={(delta) => window.__QUESTIONS__!.deltas.push(delta)}
    onOpenDocument={(id) => {
      window.__QUESTIONS__!.opened = id;
    }}
  />,
);
