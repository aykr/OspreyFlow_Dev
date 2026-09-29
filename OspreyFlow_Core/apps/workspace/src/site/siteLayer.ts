// Renders a calibrated site's image + grid directly on the `maplibregl.Map`
// `MapView.tsx` exposes via `onMapReady` — a per-investigation analyst
// layer, not a `MapProvider` registry entry (`spec/00_ARCHITECTURE.md`
// §1.2's `kind: image` is the different, ops-provisioned case; see
// `SiteCalibrationWizard.tsx`'s own docstring for the full distinction).
//
// MapLibre's native `image` source takes exactly four corner coordinates
// in TL/TR/BR/BL order — the same winding order `bilinear.ts`'s control
// points already use throughout, so no reordering happens at this
// boundary.
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

import type { ControlQuad, GridCell } from "./bilinear";

const SITE_IMAGE_SOURCE_ID = "site-image";
const SITE_IMAGE_LAYER_ID = "site-image-layer";
const SITE_GRID_SOURCE_ID = "site-grid";
const SITE_GRID_LINE_LAYER_ID = "site-grid-lines";

function imageCoordinates(
  controlPoints: ControlQuad,
): [[number, number], [number, number], [number, number], [number, number]] {
  const [tl, tr, br, bl] = controlPoints;
  return [
    [tl.lon, tl.lat],
    [tr.lon, tr.lat],
    [br.lon, br.lat],
    [bl.lon, bl.lat],
  ];
}

/** Adds or replaces the site's raster overlay. Safe to call repeatedly
 * (e.g. as the analyst adjusts a control point during calibration) —
 * removes its own previous source/layer first rather than erroring on a
 * duplicate id, since MapLibre has no "upsert" for either. */
export function setSiteImageLayer(
  map: MapLibreMap,
  imageUrl: string,
  controlPoints: ControlQuad,
): void {
  removeSiteImageLayer(map);
  map.addSource(SITE_IMAGE_SOURCE_ID, {
    type: "image",
    url: imageUrl,
    coordinates: imageCoordinates(controlPoints),
  });
  map.addLayer({
    id: SITE_IMAGE_LAYER_ID,
    type: "raster",
    source: SITE_IMAGE_SOURCE_ID,
    paint: { "raster-opacity": 0.9 },
  });
}

export function removeSiteImageLayer(map: MapLibreMap): void {
  if (map.getLayer(SITE_IMAGE_LAYER_ID)) map.removeLayer(SITE_IMAGE_LAYER_ID);
  if (map.getSource(SITE_IMAGE_SOURCE_ID))
    map.removeSource(SITE_IMAGE_SOURCE_ID);
}

function gridToGeoJSON(cells: readonly GridCell[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: cells.map((cell) => ({
      type: "Feature",
      properties: { row: cell.row, col: cell.col },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [cell.corners[0].lon, cell.corners[0].lat],
            [cell.corners[1].lon, cell.corners[1].lat],
            [cell.corners[2].lon, cell.corners[2].lat],
            [cell.corners[3].lon, cell.corners[3].lat],
            [cell.corners[0].lon, cell.corners[0].lat],
          ],
        ],
      },
    })),
  };
}

/** The grid preview (before confirming) and the persisted grid (after) are
 * rendered the same way — this has no notion of "confirmed" vs "preview",
 * that distinction lives entirely in the wizard's own state. */
export function setSiteGridLayer(
  map: MapLibreMap,
  cells: readonly GridCell[],
): void {
  const geojson = gridToGeoJSON(cells);
  const existing = map.getSource(SITE_GRID_SOURCE_ID);
  if (existing && existing.type === "geojson") {
    (existing as GeoJSONSource).setData(geojson);
    return;
  }
  removeSiteGridLayer(map);
  map.addSource(SITE_GRID_SOURCE_ID, { type: "geojson", data: geojson });
  map.addLayer({
    id: SITE_GRID_LINE_LAYER_ID,
    type: "line",
    source: SITE_GRID_SOURCE_ID,
    paint: { "line-color": "#e8eced", "line-width": 1, "line-opacity": 0.7 },
  });
}

export function removeSiteGridLayer(map: MapLibreMap): void {
  if (map.getLayer(SITE_GRID_LINE_LAYER_ID))
    map.removeLayer(SITE_GRID_LINE_LAYER_ID);
  if (map.getSource(SITE_GRID_SOURCE_ID)) map.removeSource(SITE_GRID_SOURCE_ID);
}

export function removeAllSiteLayers(map: MapLibreMap): void {
  removeSiteImageLayer(map);
  removeSiteGridLayer(map);
}

/** A one-shot click listener for the calibration wizard's "click the
 * matching point on the map" step.
 *
 * **Not `map.once("click", ...)`, and not a capture-phase listener on
 * `map.getContainer()` either** (an earlier version of this function —
 * both were tried and confirmed broken by hand against a running dev
 * server, not assumed). `MapView.tsx` renders Sigma's own canvas over
 * MapLibre's, and reading `@sigma/layer-maplibre`'s real source
 * (`sigma.getContainer().prepend(mapContainer)`, matching this module's
 * own established practice of checking third-party source rather than
 * its README) shows why: MapLibre's container is a **child** of Sigma's
 * container, so Sigma's canvas is a *sibling* of `map.getContainer()`,
 * never a descendant of it — a capture-phase listener on
 * `map.getContainer()` is never in the event's capture path for a click
 * that actually lands on Sigma's sibling canvas. The listener has to sit
 * on the element both canvases are *inside*, i.e. `map.getContainer()`'s
 * own parent (`sigma.getContainer()`, the same node `MapView.tsx`'s own
 * `containerRef` points at) — that one *is* a shared ancestor of both,
 * so a capture-phase listener there fires before either canvas gets the
 * event. `map.unproject` turns the container-relative pixel position
 * back into a `LngLat`. */
export function onNextMapClick(
  map: MapLibreMap,
  handler: (lngLat: { lng: number; lat: number }) => void,
): () => void {
  const mapContainer = map.getContainer();
  const sharedContainer = mapContainer.parentElement ?? mapContainer;
  const listener = (event: MouseEvent) => {
    const rect = mapContainer.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const lngLat = map.unproject([x, y]);
    handler({ lng: lngLat.lng, lat: lngLat.lat });
  };
  sharedContainer.addEventListener("click", listener, { capture: true, once: true });
  return () => sharedContainer.removeEventListener("click", listener, { capture: true });
}
