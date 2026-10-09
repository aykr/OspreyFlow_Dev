// The Ingest Studio's row-template canvas on its own (spec 09 §4), driven by buttons standing in for
// MapScreen's state: three entities and one link, selected as it is just after it was made. *Pick
// c as a link's start* sets what MapScreen sets on the first click of *+ link*.
import { useState } from "react";
import type Sigma from "sigma";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { MapCanvas, type MapSelection } from "../src/ingest/map/MapCanvas";
import type { OntologySchema, RowTemplate } from "../../../packages/schemas/generated";

const ONTOLOGY = {
  version: 13,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle" },
    { name: "Endpoint", pole_class: "object", channel: "teal", shape: "hexagon" },
    { name: "Device", pole_class: "object", channel: "plum", shape: "square" },
  ],
  edge_types: [],
} as unknown as OntologySchema;

/** `?later=1`: the third entity is added after the link, as the Studio's *+ entity* does. */
const LATER = new URLSearchParams(window.location.search).get("later") === "1";

const TEMPLATE = {
  entities: [
    { ref: "subscriber", pole_class: "person", type: "Person", on_match: "create", properties: {} },
    { ref: "phone", pole_class: "object", type: "Endpoint", on_match: "create", properties: {} },
    { ref: "handset", pole_class: "object", type: "Device", on_match: "create", properties: {} },
  ],
  edges: [{ type: "USES", from: "subscriber", to: "phone", properties: {} }],
} as unknown as RowTemplate;

declare global {
  interface Window {
    __MAP__?: { positionOf: (ref: string) => { x: number; y: number } | null };
  }
}
let sigmaInstance: Sigma | null = null;
window.__MAP__ = {
  positionOf: (ref) => {
    if (!sigmaInstance || !sigmaInstance.getGraph().hasNode(ref)) return null;
    const data = sigmaInstance.getNodeDisplayData(ref);
    return data ? sigmaInstance.framedGraphToViewport({ x: data.x, y: data.y }) : null;
  },
};

/** `?real=1`: the canvas wired as MapScreen wires it, so a click on a node is handled as there. */
const REAL = new URLSearchParams(window.location.search).get("real") === "1";

function Harness() {
  const [template, setTemplate] = useState<RowTemplate>(() =>
    LATER ? { ...TEMPLATE, entities: TEMPLATE.entities.slice(0, 2) } : TEMPLATE,
  );
  const [selection, setSelection] = useState<MapSelection>({ kind: "edge", index: 0 });
  const [linkFromRef, setLinkFromRef] = useState<string | null>(null);
  return (
    <div style={{ display: "grid", gridTemplateRows: "auto 1fr", height: "100%" }}>
      <div data-harness-only="">
        <button type="button" onClick={() => setLinkFromRef("handset")}>Pick handset as a link's start</button>
        <button type="button" onClick={() => setSelection(null)}>Select nothing</button>
        <button
          type="button"
          onClick={() => {
            setTemplate(TEMPLATE);
            setSelection({ kind: "entity", ref: "handset" });
          }}
        >
          Add handset
        </button>
      </div>
      <MapCanvas
        template={template}
        ontology={ONTOLOGY}
        selection={selection}
        linkFromRef={linkFromRef}
        onSelect={(sel) => {
          if (REAL && sel?.kind === "entity" && linkFromRef === null) setLinkFromRef(sel.ref);
          else setSelection(sel);
        }}
        onReady={(sigma) => {
          sigmaInstance = sigma;
        }}
        onBackgroundClick={() => setSelection(null)}
      />
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);
