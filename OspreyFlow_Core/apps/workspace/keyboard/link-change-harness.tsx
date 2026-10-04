// Link-change keyboard harness (ADR-080): the Inspector's *Change this link* form is a
// keyboard-driven surface of its own, so — as for the link notes (`link-notes-harness.tsx`) — it gets
// a small harness and a spec (`link-change.spec.ts`) that intercepts the change route at the
// transport. It mounts `LinkChange` directly, the component `Inspector` renders under a selected
// link. `?signal=1` mounts it as if the link menu's *Change link…* had just been chosen.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { LinkChange } from "../src/inspector/LinkChange";
import type { LinkChangeResult } from "../src/inspector/linkChangeApi";
import type { Edge, EdgeTypeDef } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    /** The last result the form handed back to its caller, or null while it has not saved. */
    __CHANGED__?: LinkChangeResult | null;
  }
}
window.__CHANGED__ = null;

const EDGE_TYPES: EdgeTypeDef[] = [
  { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], basis: "direct" },
  {
    name: "COLLEAGUE_OF",
    from: ["Person"],
    to: ["Person"],
    properties: [{ name: "role", type: "string" }],
    basis: "direct",
  },
  { name: "SAME_AS", from: ["*"], to: ["*"], system: true, basis: "probabilistic" },
];

const edge: Edge = {
  id: "e1",
  type: "ASSOCIATE_OF",
  source: "a",
  target: "b",
  occurrences: 3,
  provenance: {
    state: "asserted",
    sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
    first_seen: "2026-01-01T00:00:00Z",
  },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
};

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

const signal = Number(new URLSearchParams(window.location.search).get("signal") ?? "0");

createRoot(container).render(
  <>
    <LinkChange
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      investigationId="inv-1"
      edge={edge}
      sourceType="Person"
      targetType="Person"
      edgeTypes={EDGE_TYPES}
      openSignal={signal}
      onChanged={(result) => {
        window.__CHANGED__ = result;
      }}
    />
    <button id="after-form">After the form</button>
  </>,
);
