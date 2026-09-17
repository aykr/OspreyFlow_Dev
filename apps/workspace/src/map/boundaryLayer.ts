// Renders the drawn-boundary spatial filter's live preview on the
// `maplibregl.Map` `MapView.tsx` exposes via `onMapReady` — `07_BUILD_PLAN.md`
// Phase 5 Checkpoint 3c, `02_GLASS_FRONTEND.md` §3.5's "a drawn or selected
// boundary is a spatial filter like any other". Mirrors `site/siteLayer.ts`'s
// own GeoJSON source/layer shape exactly (same "remove-then-add, since
// MapLibre has no upsert" idiom), rendered as a `LineString` while fewer
// than three points are placed and a closed `Polygon` once there are
// enough to actually enclose an area.
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

import { BRASS_HEX } from "../color/tokens";

const BOUNDARY_SOURCE_ID = "ospreyflow-boundary-draw";
const BOUNDARY_FILL_LAYER_ID = "ospreyflow-boundary-draw-fill";
const BOUNDARY_LINE_LAYER_ID = "ospreyflow-boundary-draw-line";

export interface LngLat {
  lng: number;
  lat: number;
}

function boundaryGeoJSON(points: readonly LngLat[]): GeoJSON.Feature {
  const coordinates = points.map((p) => [p.lng, p.lat]);
  if (points.length < 3) {
    return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } };
  }
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "Polygon", coordinates: [[...coordinates, coordinates[0]!]] },
  };
}

/** Safe to call on every click while drawing — replaces the previous
 * preview's data rather than tearing down and re-adding the source/layer,
 * the same `existing.type === "geojson"` fast path `site/siteLayer.ts`'s
 * `setSiteGridLayer` already uses. */
export function setBoundaryDrawLayer(map: MapLibreMap, points: readonly LngLat[]): void {
  const geojson = boundaryGeoJSON(points);
  const existing = map.getSource(BOUNDARY_SOURCE_ID);
  if (existing && existing.type === "geojson") {
    (existing as GeoJSONSource).setData(geojson);
    return;
  }
  map.addSource(BOUNDARY_SOURCE_ID, { type: "geojson", data: geojson });
  map.addLayer({
    id: BOUNDARY_FILL_LAYER_ID,
    type: "fill",
    source: BOUNDARY_SOURCE_ID,
    filter: ["==", ["geometry-type"], "Polygon"],
    paint: { "fill-color": BRASS_HEX, "fill-opacity": 0.15 },
  });
  map.addLayer({
    id: BOUNDARY_LINE_LAYER_ID,
    type: "line",
    source: BOUNDARY_SOURCE_ID,
    paint: { "line-color": BRASS_HEX, "line-width": 2 },
  });
}

export function removeBoundaryDrawLayer(map: MapLibreMap): void {
  if (map.getLayer(BOUNDARY_FILL_LAYER_ID)) map.removeLayer(BOUNDARY_FILL_LAYER_ID);
  if (map.getLayer(BOUNDARY_LINE_LAYER_ID)) map.removeLayer(BOUNDARY_LINE_LAYER_ID);
  if (map.getSource(BOUNDARY_SOURCE_ID)) map.removeSource(BOUNDARY_SOURCE_ID);
}
