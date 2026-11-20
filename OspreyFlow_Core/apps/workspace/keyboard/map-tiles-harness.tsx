// The Glass's real Map view (`map/MapView.tsx`) over a vector basemap read through the `pmtiles://`
// protocol, for `map-tiles.spec.ts` (slice GG6). The archive is synthetic (`mapTilesFixture.ts`); the
// spec answers its requests, as a Conduit's ranged route would, and refuses any without the bearer token
// this page gives the Map view (a Conduit requires one on every route; `src/map/pmtilesAuth.ts`).
// Three located nodes, as the other map harnesses have. The page tells the spec which MapLibre it runs (`window.__MAPLIBRE_VERSION__`, read
// from the library itself) and exposes the map on `window.__MAP__`.
import Graph from "graphology";
import { getVersion } from "maplibre-gl";
import type { Map as MapLibreMap } from "maplibre-gl";
import { createRoot } from "react-dom/client";

import "../../../packages/design/tokens.css";
import "../src/design/primitives.css";
import { MapView } from "../src/map/MapView";
import type { WorkingSetGraph } from "../src/workingset/store";
import type { PublicMapProvider } from "../../../packages/schemas/generated";
import { applyHarnessBrand } from "./brandHarness";
import { FIXTURE_BEARER_TOKEN } from "./mapTilesToken";

declare global {
  interface Window {
    __MAP__?: MapLibreMap;
    __MAPLIBRE_VERSION__?: string;
    /** Whether this page is a production bundle or the dev server's, from the build itself. */
    __BUNDLE__?: "production" | "development";
  }
}

/** Where the spec serves the synthetic archive; a path on this page's own origin, as a Conduit's is. */
export const SOURCE_PATH = "/fixture/map-tiles.pmtiles";

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

const PROVIDER = {
  id: "fixture-vector",
  label: "Synthetic vector tiles",
  kind: "vector",
  style: "bundled:osprey-dark",
  attribution: "Synthetic tiles ©",
  licence_id: "none",
  licence_note: "",
  client_scope: "open",
  source: SOURCE_PATH,
} as unknown as PublicMapProvider;

window.__MAPLIBRE_VERSION__ = getVersion();
window.__BUNDLE__ = import.meta.env.PROD ? "production" : "development";

void applyHarnessBrand().then(() => {
  createRoot(document.getElementById("root")!).render(
    <main>
      <h1 style={{ position: "absolute", left: -10000 }} data-harness-only="">Map tiles harness</h1>
      <div style={{ width: 1000, height: 700, position: "relative" }}>
        <MapView
          graph={graph}
          provider={PROVIDER}
          nodeCoordinates={COORDINATES}
          onMapReady={onMapReady}
          apiBaseUrl={window.location.origin}
          bearerToken={FIXTURE_BEARER_TOKEN}
        />
      </div>
    </main>,
  );
});
