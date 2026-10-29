// The Glass's map view (`map/MapView.tsx`) with three located nodes, close together as a prison's
// yards are, and a button that shrinks the map's box as opening the timeline does. The map is
// exposed on `window.__MAP__` so a spec can read where its camera is.
import { useState } from "react";
import Graph from "graphology";
import type { Map as MapLibreMap } from "maplibre-gl";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { MapView } from "../src/map/MapView";
import type { WorkingSetGraph } from "../src/workingset/store";
import type { PublicMapProvider } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __MAP__?: MapLibreMap;
  }
}

const YARDS: Record<string, { lat: number; lng: number }> = {
  "yard-03": { lat: 51.4309, lng: -1.1503 },
  "yard-04": { lat: 51.4305, lng: -1.1478 },
  "yard-05": { lat: 51.4296, lng: -1.1489 },
};

const graph: WorkingSetGraph = new Graph({ multi: true, type: "mixed" });
for (const id of Object.keys(YARDS)) {
  graph.addNode(id, {
    data: {
      id,
      type: "Location",
      properties: { name: id },
      provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
      handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
    },
  } as never);
}

// Stable across renders, as the app's are: a new map would make the view mount again.
const COORDINATES = new Map(Object.entries(YARDS));
const onMapReady = (map: MapLibreMap) => {
  window.__MAP__ = map;
};

// A raster provider whose tiles never arrive: the camera, not the picture, is what is checked.
const PROVIDER = {
  id: "harness",
  label: "Harness",
  kind: "raster",
  style: "bundled:osprey-raster-overlay",
  attribution: "Harness",
  licence_id: "none",
  licence_note: "",
  client_scope: "open",
  source: "http://map-view.invalid/{z}/{x}/{y}.png",
} as unknown as PublicMapProvider;

function Harness() {
  const [height, setHeight] = useState(700);
  return (
    <div>
      <button type="button" onClick={() => setHeight(560)}>
        Shrink the map
      </button>
      <div style={{ width: 1000, height, position: "relative" }}>
        <MapView
          graph={graph}
          provider={PROVIDER}
          nodeCoordinates={COORDINATES}
          onMapReady={onMapReady}
        />
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
