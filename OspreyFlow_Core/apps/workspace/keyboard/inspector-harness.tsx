// The Inspector on its own (ADR-096), a link selected between two people: each part folds under
// its header. A button stands in for the link menu's *Add a note*, which hands over by raising the
// note signal, as `App.tsx` does; the menu's own hand-over is proved in `link-menu.spec.ts`.
import Graph from "graphology";
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import { applyHarnessBrand } from "./brandHarness";
import "../src/design/primitives.css";
import { Inspector } from "../src/inspector/Inspector";
import type { Edge, EdgeTypeDef, Node } from "../../../packages/schemas/generated";

const person = (id: string, name: string): Node =>
  ({
    id,
    type: "Person",
    properties: { family_name: name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  }) as unknown as Node;

const edge = {
  id: "e1",
  type: "ASSOCIATE_OF",
  source: "a",
  target: "b",
  occurrences: 2,
  provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
} as unknown as Edge;

const EDGE_TYPES: EdgeTypeDef[] = [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], basis: "direct" }];

declare global {
  interface Window {
    __INSPECTOR__?: { deltas: number[]; expanded: string[] };
  }
}
window.__INSPECTOR__ = { deltas: [], expanded: [] };

/** `?view=node`: a person selected, with who shares contacts with them (ADR-100 Amendment 7). */
const NODE_VIEW = new URLSearchParams(window.location.search).get("view") === "node";
/** `?view=picture`: a car selected, which may have a picture of its own (ADR-105). */
const PICTURE_VIEW = new URLSearchParams(window.location.search).get("view") === "picture";

const car = { ...person("car-1", "unused"), type: "Vehicle", properties: {} } as unknown as Node;

function Harness() {
  const [noteSignal, setNoteSignal] = useState(0);
  if (PICTURE_VIEW) {
    return (
      <Inspector
        node={car}
        picture={{
          apiBaseUrl: "http://keyboard-test.invalid",
          bearerToken: "unused",
          investigationId: "inv-1",
          types: new Set(["Vehicle"]),
          onDelta: (delta) => window.__INSPECTOR__!.deltas.push((delta as { seq: number }).seq),
        }}
      />
    );
  }
  if (NODE_VIEW) {
    return (
      <Inspector
        node={person("a", "Ashby")}
        onExpand={(id) => window.__INSPECTOR__!.expanded.push(id)}
        neighbourhoodRisk={{ apiBaseUrl: "http://keyboard-test.invalid", bearerToken: "unused", investigationId: "inv-1" }}
        sharedContacts={{
          apiBaseUrl: "http://keyboard-test.invalid",
          bearerToken: "unused",
          investigationId: "inv-1",
          edgeTypes: EDGE_TYPES,
          onDelta: (delta) => window.__INSPECTOR__!.deltas.push(delta.seq),
        }}
      />
    );
  }
  return (
    <>
      <button type="button" data-harness-only="" onClick={() => setNoteSignal((n) => n + 1)}>
        Hand over: Add a note
      </button>
      <Inspector
        node={null}
        link={{ edge, source: person("a", "Ashby"), target: person("b", "Holloway"), directed: false }}
        assessment={{
          apiBaseUrl: "http://keyboard-test.invalid",
          bearerToken: "unused",
          investigationId: "inv-1",
          workingSetGraph: new Graph(),
          onHighlightNodes: () => undefined,
        }}
        linkEditing={{
          edgeTypes: EDGE_TYPES,
          openChangeSignal: 0,
          openNoteSignal: noteSignal,
          openEventsSignal: 0,
          onChanged: () => undefined,
          // ADR-102: the deployment's scheme, so the handling can be changed.
          handlingScheme: {
            name: "uk-le",
            classification: ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"],
            handling_codes: {
              P: { label: "Lawful sharing permitted", dissemination: "permitted" },
              C: { label: "Conditions apply", dissemination: "conditional" },
              R: { label: "Recipient restricted", dissemination: "restricted" },
            },
            action_codes: {},
            sanitisation_codes: {},
          },
        }}
      />
    </>
  );
}

await applyHarnessBrand();

/** `?strength=1` (ADR-139 decision 9): the link's connection strength explained, answered by the page
 * itself and opened, for the axe scan. Synthetic (rule 9). */
const STRENGTH_ANSWERS = {
  links: [{
    edge_id: "e1", edge_type: "ASSOCIATE_OF", base_weight: 0.62, strength: 0.71, parameter_set: "3/default", heavy: 10,
    fixed: null, occurrences: 2, last_seen: "2026-04-18T00:00:00Z",
    applied: [{ id: "incident-source", label: "Evidenced by an assault, disorder or find", change: "add", size: 0.1348,
      layer: "file", record_kind: "Incident" }],
  }],
  legend: { influencers: [], direct_link_types: [], switched_off: [], rarity_note: "" },
}; // prettier-ignore
const RARITY_ANSWERS = {
  scope: "dataset",
  node_values: {},
  pairs: [{ a: "a", b: "b", score: 2.31, dataset: "prison-intelligence", shared: [
    { node: { ...person("x1", "unused"), type: "Endpoint", properties: { value_normalised: "+441234567891" } }, score: 2.31 },
    { node: { ...person("x2", "unused"), type: "Organisation", properties: { name: "Fenwick Moor Prison" } }, score: 0 },
  ] }],
}; // prettier-ignore
const STRENGTH_OPEN = new URLSearchParams(window.location.search).get("strength") === "1";
if (STRENGTH_OPEN) {
  window.fetch = async (input: RequestInfo | URL) => {
    const url = String(input);
    // The link's other parts read as a link with none of them has it.
    const body = url.endsWith("/connection-strength")
      ? STRENGTH_ANSWERS
      : url.endsWith("/rarity")
        ? RARITY_ANSWERS
        : url.includes("/notes")
          ? { notes: [] }
          : url.includes("/history")
            ? { changes: [], truncated: false }
            : { total: 0, offset: 0, limit: 50, events: [] };
    return new Response(JSON.stringify(body), { status: 200 });
  };
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);

if (STRENGTH_OPEN) {
  for (let i = 0; i < 40; i++) {
    await new Promise((resolve) => setTimeout(resolve, 50));
    const header = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Connection strength");
    if (header) {
      header.click();
      break;
    }
  }
}
