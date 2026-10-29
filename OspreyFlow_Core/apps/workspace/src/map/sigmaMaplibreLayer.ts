// The graph layer drawn over the map: `@sigma/layer-maplibre` 3.0.0's `bindMaplibreLayer`, kept here
// with two changes (ADR-086 Amendment 1). Copyright (C) 2013-2024, Alexis Jacomy, Guillaume Plique,
// Benoît Simard, https://www.sigmajs.org, under the MIT licence (NOTICE).
//
// The change: the library flipped a node's y as the map container's height less its Mercator y,
// so a change of height moved every node by that many Mercator units (about a hundred times the
// world's height for 140 pixels). Its own resize then re-centred sigma before sigma had redrawn at
// the new projection: opening the timeline over a drawn map put the camera at latitude -85 and the
// map went blank. Any constant flips y as well, so 1 is used, and a node's graph position no
// longer depends on the size of the box. The second, in `fnOnResize`, keeps the area shown rather
// than only its centre. Everything else is the library's, line for line.
import { LngLat, LngLatBounds, Map, MercatorCoordinate, type MapOptions } from "maplibre-gl";
import type Sigma from "sigma";

/** A geographic position as the graph layer stores it: x and y in Mercator units, y flipped. */
export function latlngToGraph(coord: { lat: number; lng: number }): { x: number; y: number } {
  const data = MercatorCoordinate.fromLngLat(coord);
  // Y are reversed between geo / sigma
  return { x: data.x, y: 1 - data.y };
}

export function graphToLatlng(coords: { x: number; y: number }): { lat: number; lng: number } {
  const data = new MercatorCoordinate(coords.x, 1 - coords.y, 0).toLngLat();
  return { lat: data.lat, lng: data.lng };
}

/** BBOX sync : map to sigma */
function syncSigmaWithMap(sigma: Sigma, map: Map): void {
  const center = sigma.viewportToFramedGraph(sigma.graphToViewport(latlngToGraph(map.getCenter())));
  const mapBound = map.getBounds();
  const northEast = sigma.graphToViewport(latlngToGraph(mapBound.getNorthEast()));
  const southWest = sigma.graphToViewport(latlngToGraph(mapBound.getSouthWest()));
  const viewportBoundDimension = {
    width: Math.abs(northEast.x - southWest.x),
    height: Math.abs(northEast.y - southWest.y),
  };
  const viewportDim = sigma.getDimensions();
  const ratio =
    Math.min(viewportBoundDimension.width / viewportDim.width, viewportBoundDimension.height / viewportDim.height) *
    sigma.getCamera().getState().ratio;
  sigma.getCamera().setState({ ...center, ratio });
}

/** BBOX sync : sigma to map */
function syncMapWithSigma(sigma: Sigma, map: Map): void {
  const viewportDimensions = sigma.getDimensions();
  const graphBottomLeft = sigma.viewportToGraph({ x: 0, y: viewportDimensions.height }, { padding: 0 });
  const graphTopRight = sigma.viewportToGraph({ x: viewportDimensions.width, y: 0 }, { padding: 0 });
  const geoSouthWest = graphToLatlng(graphBottomLeft);
  const geoNorthEast = graphToLatlng(graphTopRight);
  map.fitBounds(new LngLatBounds([geoSouthWest, geoNorthEast]), { duration: 0 });
}

/**
 * On the graph, we store the 2D projection of the geographical lat/long.
 *
 * @param sigma The sigma instance
 * @param opts.mapOptions Options that will be provided to map constructor.
 * @param opts.getNodeLatLng Function to retrieve lat/long values from a node's attributes (default is lat & lng)
 */
export default function bindMaplibreLayer(
  sigma: Sigma,
  opts?: {
    mapOptions?: Omit<MapOptions, "container">;
    getNodeLatLng?: (attrs: Record<string, unknown>) => { lat: number; lng: number };
  },
): { clean: () => void; map: Map; updateGraphCoordinates: (graph: ReturnType<Sigma["getGraph"]>) => void } {
  let isKilled = false;
  const prevSigmaSettings = sigma.getSettings();

  const mapLayerName = "layer-maplibre";
  const mapContainer = sigma.createLayer(mapLayerName, "div", {
    style: { position: "absolute", inset: "0" },
    // 'edges' is the first sigma layer
    beforeLayer: "edges",
  });
  sigma.getContainer().prepend(mapContainer);

  const map = new Map({
    container: mapContainer,
    style: "https://demotiles.maplibre.org/style.json",
    center: [0, 0],
    zoom: 1,
    minPitch: 0,
    maxPitch: 0,
    ...(opts?.mapOptions ?? {}),
  });

  // `stagePadding: 0` is mandatory, so the bbox of the map & Sigma is the same.
  sigma.setSetting("stagePadding", 0);
  // disable camera rotation
  sigma.setSetting("enableCameraRotation", false);

  function updateGraphCoordinates(graph: ReturnType<Sigma["getGraph"]>): void {
    graph.updateEachNodeAttributes((_node, attrs) => {
      const coords = latlngToGraph(
        opts?.getNodeLatLng ? opts.getNodeLatLng(attrs) : { lat: attrs.lat as number, lng: attrs.lng as number },
      );
      return { ...attrs, x: coords.x, y: coords.y };
    });
  }

  function fnSyncMapWithSigma(): void {
    syncMapWithSigma(sigma, map);
  }

  function fnSyncSigmaWithMap(): void {
    if (!sigma.getCamera().isAnimated() && !map.isMoving()) {
      // Check that sigma & map are already in sync
      const southWest = graphToLatlng(sigma.viewportToGraph({ x: 0, y: sigma.getDimensions().height }));
      const northEast = graphToLatlng(sigma.viewportToGraph({ x: sigma.getDimensions().width, y: 0 }));
      const diff = Math.max(
        map.getBounds().getSouthWest().distanceTo(new LngLat(southWest.lng, southWest.lat)),
        map.getBounds().getNorthEast().distanceTo(new LngLat(northEast.lng, northEast.lat)),
      );
      if (diff > 1) syncSigmaWithMap(sigma, map);
    }
  }

  // When sigma is resized, the zoom bounds are computed again.
  function fnOnResize(): void {
    // Avoid sync map with sigma while we do the resize, otherwise there is a side effect...
    sigma.off("afterRender", fnSyncMapWithSigma);
    // The second change (ADR-086 Amendment 1): the area shown is kept, not only its centre. Kept
    // by its centre, a shorter box stepped the camera in by about one zoom level, and two of the
    // three yards a demo had drawn left the view.
    const shown = map.getBounds();
    map.once("resize", () => {
      map.fitBounds(shown, { duration: 0 });
      updateGraphCoordinates(sigma.getGraph());
      fnSyncSigmaWithMap();
      // Re-enable the map sync with sigma in the next frame. Sigma first draws at its new size and
      // takes its camera from the map, so the map keeps the area it was fitted to; the library
      // copied sigma's camera, framed for the old size, onto the map instead (ADR-086 Amendment 1).
      setTimeout(() => {
        sigma.refresh();
        syncSigmaWithMap(sigma, map);
        sigma.on("afterRender", fnSyncMapWithSigma);
      }, 0);
    });
    map.resize();
  }

  function clean(): void {
    if (!isKilled) {
      isKilled = true;
      map.off("moveend", fnSyncSigmaWithMap);
      map.remove();
      sigma.killLayer(mapLayerName);
      sigma.off("afterRender", fnSyncMapWithSigma);
      sigma.off("resize", fnOnResize);
      sigma.setSetting("stagePadding", prevSigmaSettings.stagePadding);
      sigma.setSetting("enableCameraRotation", prevSigmaSettings.enableCameraRotation);
    }
  }

  updateGraphCoordinates(sigma.getGraph());

  map.once("load", () => {
    // Compute sigma ratio bounds; must be done after the first map render
    map.once("moveend", () => {
      fnSyncSigmaWithMap();
    });
    // Do the first sync
    fnSyncMapWithSigma();
    // At each render of sigma, we do the map sync
    sigma.on("afterRender", fnSyncMapWithSigma);
    sigma.on("resize", fnOnResize);
    sigma.on("kill", clean);
    // Keep sigma camera on the map
    map.on("moveend", fnSyncSigmaWithMap);
  });

  return { clean, map, updateGraphCoordinates };
}
