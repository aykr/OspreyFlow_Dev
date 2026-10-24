// Deck capture — the real geospatial view (`MapView`, MapLibre over the GB PMTiles basemap) with
// Operation Ledger's places. The basemap is served by the capture rig's own
// static server; the glyphs are fulfilled from disk by the capture spec. Tier 1 data only.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { MapView } from "../src/map/MapView";
import { createWorkingSet } from "../src/workingset/store";
import type { PublicMapProvider } from "../../../packages/schemas/generated";
import { COORDINATES, FRAUD_EDGES, FRAUD_NODES } from "./fraudFixture";

const workingSet = createWorkingSet();
workingSet.store
  .getState()
  .applyDelta({ seq: 1, op: "snapshot", nodes: FRAUD_NODES, edges: FRAUD_EDGES });

const provider: PublicMapProvider = {
  id: "deck-local-gb",
  label: "Great Britain (local build)",
  kind: "vector",
  style: "bundled:osprey-dark",
  attribution: "© OpenStreetMap contributors",
  licence_id: "ODbL-1.0",
  licence_note: "local Planetiler build",
  client_scope: "deck-capture",
  source: "http://localhost:5188/great-britain.pmtiles",
} as PublicMapProvider;

const nodeCoordinates = new Map(Object.entries(COORDINATES));

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(
  <div style={{ width: "100vw", height: "100vh" }}>
    <MapView graph={workingSet.graph} provider={provider} nodeCoordinates={nodeCoordinates} />
  </div>,
);
