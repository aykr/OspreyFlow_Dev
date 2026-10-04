// The full-screen reader (ADR-092) on its own: `reader.spec.ts` intercepts the reader, extract and
// accept routes and walks it by keyboard. Closing records itself, as the Glass would return focus.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { OntologyRegistry } from "../src/ontology/schema";
import { DocumentReader } from "../src/reader/DocumentReader";

declare global {
  interface Window {
    __READER__?: { closed: number; deltas: unknown[] };
  }
}
window.__READER__ = { closed: 0, deltas: [] };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <DocumentReader
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    documentId="email:ev-1"
    ontology={new OntologyRegistry({ version: 1, entity_types: [], edge_types: [] } as never)}
    labelOf={(id) => ({ a: "alice@enron.com", b: "bob@enron.com" })[id] ?? id}
    onClose={() => {
      window.__READER__!.closed += 1;
    }}
    onDelta={(delta) => {
      window.__READER__!.deltas.push(delta);
    }}
  />,
);
