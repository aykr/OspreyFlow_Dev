// Where the map opens. The graph layer (`@sigma/layer-maplibre`) fits the map to the nodes it
// plots; with none, it fits the camera to an undefined box and MapLibre draws nothing (8 October
// 2026, the HMP case, whose locations are on a site plan). So with nothing to plot the map opens on
// the basemap's own centre, from its PMTiles header, and the graph layer is not bound at all.

/** The part of a PMTiles header that says where the basemap is. */
export interface BasemapCentre {
  centerLon: number;
  centerLat: number;
  centerZoom: number;
}

export type MapStart =
  | { kind: "fit" }
  | { kind: "view"; center: [number, number]; zoom: number };

export function mapStart(plotted: number, centre: BasemapCentre | null): MapStart {
  if (plotted > 0) return { kind: "fit" };
  if (centre === null) return { kind: "view", center: [0, 0], zoom: 1 };
  return { kind: "view", center: [centre.centerLon, centre.centerLat], zoom: centre.centerZoom };
}
