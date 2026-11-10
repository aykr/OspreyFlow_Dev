// The Glass's map view (`map/MapView.tsx`) with three located nodes, close together as a prison's
// yards are, and a button that shrinks the map's box as opening the timeline does. The map is
// exposed on `window.__MAP__` so a spec can read where its camera is.
//
// P4: two basemaps to switch between (each a raster whose tiles never arrive: what is checked is
// which source the map is drawn from, not the picture) and a place search answered by a stand-in for
// the case's place route, which records each query on `window.__PLACE_QUERIES__`. `?searched=1`
// draws the search's answer already shown, for the axe scan (`a11y/every-harness.spec.ts`), and
// `?searched=more` and `?searched=fail` its "more match" and refused words;
// `?brand=govuk` the GOV.UK theme (`brandHarness.ts`).
//
// P6: the case's gazetteers beside the search, answered by a stand-in for the Conduit's routes that
// records each change on `window.__GAZETTEER_CALLS__` (synthetic names, rule 9). `?gazetteers=`
// draws a state for the axe scan: `added` (one added, one not), `reader` (no `run_pipelines`, so
// no change offered), `nothing`, `composite` and `unbuilt` (the three empty cases), `refused` (a
// change the Conduit refuses).
import { useState } from "react";
import Graph from "graphology";
import type { Map as MapLibreMap } from "maplibre-gl";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { MapView } from "../src/map/MapView";
import type { GazetteerControls } from "../src/map/MapControls";
import { GazetteersFailed, type GazetteerPanelState } from "../src/map/gazetteers";
import { PlaceSearchFailed } from "../src/map/places";
import type { WorkingSetGraph } from "../src/workingset/store";
import type { MapPlace, PublicMapProvider } from "../../../packages/schemas/generated";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __MAP__?: MapLibreMap;
    __PLACE_QUERIES__?: string[];
    __GAZETTEER_CALLS__?: string[];
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
  attribution: "Harness tiles ©",
  licence_id: "none",
  licence_note: "",
  client_scope: "open",
  source: "http://map-view.invalid/{z}/{x}/{y}.png",
} as unknown as PublicMapProvider;
// A second, hosted one, proxied as a tier-3 provider is: no source of its own in the Glass.
const HOSTED = {
  ...PROVIDER,
  id: "harness-hosted",
  label: "Hosted streets",
  attribution: "Hosted streets ©",
  client_scope: "per-deployment",
  source: null,
} as unknown as PublicMapProvider;
const PROVIDERS = [PROVIDER, HOSTED];

// Synthetic places (rule 9): what the case's gazetteer holds in this harness.
const GAZETTEER: MapPlace[] = [
  { id: "place-cranford", name: "Cranford", lon: -0.459, lat: 51.488 },
  { id: "place-cranbrook", name: "Cranbrook", lon: 0.533, lat: 51.096 },
];
window.__PLACE_QUERIES__ = [];
async function searchPlaces(query: string) {
  window.__PLACE_QUERIES__!.push(query);
  // Two answers only the axe states ask for: a scan filled by the case's own places, and a refusal.
  if (query === "zz-more") return { places: [], more: true };
  if (query === "zz-fail") throw new PlaceSearchFailed("The place search failed (HTTP 500). Try again.");
  const q = query.toLowerCase();
  return { places: GAZETTEER.filter((p) => p.name.toLowerCase().includes(q)), more: false };
}

// Synthetic gazetteers of the harness's unit (rule 9): names only, as the Conduit sends them.
const REMOVED_WORDS =
  "The gazetteer is removed: its places stay in this dataset as its own, and the map's place " +
  "search no longer offers them. A re-build no longer refreshes them; adding it again does.";
const gazetteerState = new URLSearchParams(window.location.search).get("gazetteers") ?? "";
let held = [
  { dataset_id: "gazetteer-harness-towns", name: "Harness towns", added: gazetteerState === "added" },
  { dataset_id: "gazetteer-harness-villages", name: "Harness villages", added: false },
];
window.__GAZETTEER_CALLS__ = [];
const EMPTY: Record<string, GazetteerPanelState> = {
  nothing: { state: "reads_nothing" },
  composite: { state: "not_one_source" },
  unbuilt: { state: "none_built" },
};
const GAZETTEERS: GazetteerControls = {
  load: async () =>
    EMPTY[gazetteerState] ?? { state: "ready", datasetId: "ds-harness", gazetteers: held },
  add: async (datasetId, gazetteerId) => {
    window.__GAZETTEER_CALLS__!.push(`PUT ${datasetId} ${gazetteerId}`);
    if (gazetteerState === "refused") {
      throw new GazetteersFailed(
        "You may not change this dataset's gazetteers: it needs the right to run pipelines.",
      );
    }
    held = held.map((g) => (g.dataset_id === gazetteerId ? { ...g, added: true } : g));
    return { gazetteers: held, said: null };
  },
  remove: async (datasetId, gazetteerId) => {
    window.__GAZETTEER_CALLS__!.push(`DELETE ${datasetId} ${gazetteerId}`);
    held = held.map((g) => (g.dataset_id === gazetteerId ? { ...g, added: false } : g));
    return { gazetteers: held, said: REMOVED_WORDS };
  },
  mayChange: gazetteerState !== "reader",
};

function Harness() {
  const [height, setHeight] = useState(700);
  return (
    <main>
      <h1 style={{ position: "absolute", left: -10000 }}>Map view harness</h1>
      <button type="button" onClick={() => setHeight(560)}>
        Shrink the map
      </button>
      <div style={{ width: 1000, height, position: "relative" }}>
        <MapView
          graph={graph}
          provider={PROVIDER}
          providers={PROVIDERS}
          searchPlaces={searchPlaces}
          gazetteers={GAZETTEERS}
          nodeCoordinates={COORDINATES}
          onMapReady={onMapReady}
        />
      </div>
    </main>
  );
}

void applyHarnessBrand().then(() => {
  createRoot(document.getElementById("root")!).render(<Harness />);
  const searched = new URLSearchParams(window.location.search).get("searched") ?? "";
  const typed = ({ "1": "cran", more: "zz-more", fail: "zz-fail" } as Record<string, string>)[searched];
  if (gazetteerState === "refused") {
    // The harness's own hand: ask for a change, so the refusal's words are drawn for the scan.
    const press = () => {
      const add = document.querySelector<HTMLButtonElement>('button[aria-label="Add Harness towns"]');
      if (!add) return void setTimeout(press, 50);
      add.click();
    };
    press();
  }
  if (typed) {
    // The harness's own hand, not the product's: type a name and submit, so the answer is drawn.
    const fill = () => {
      const input = document.querySelector<HTMLInputElement>('form[role="search"] input');
      if (!input) return void setTimeout(fill, 50);
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      set.call(input, typed);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.form!.requestSubmit();
    };
    fill();
  }
});
