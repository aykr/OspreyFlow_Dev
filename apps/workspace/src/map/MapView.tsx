// The MapLibre view — `docs/02_GLASS_FRONTEND.md` §3.5, ADR-014
// (`docs/06_DECISIONS.md`), `docs/07_BUILD_PLAN.md` Phase 5.
//
// **A separate Sigma instance over a local node clone, not the shared
// working-set graph.** `@sigma/layer-maplibre`'s `bindMaplibreLayer`
// mutates `x`/`y` on every node in whatever graph it is bound to
// (`updateGraphCoordinates`, confirmed by reading the package's real
// source, not assumed from its README) — sharing `GlassCanvas`'s
// graphology instance would have this view's geographic projection
// silently corrupt the Graph view's own layout the moment both had ever
// mounted. `docs/02_GLASS_FRONTEND.md` §2's "Graph · Map · Matrix ...
// three renderings of the same working set" holds at the conceptual
// level (same node/edge membership, same selection) without requiring one
// literal shared graphology instance a third-party plugin was never
// designed to share.
//
// **Only nodes with a resolved coordinate are plotted — the rest are
// absent, not dimmed.** Resolving a `Location.geometry_ref`
// (`01_DOMAIN_MODEL.md` §7.1) to a WGS84 point is
// `AnalyticsPort.get_geometries`, exposed over HTTP this checkpoint
// (`POST /v1/analytics/geometries`) and called from `App.tsx` via
// `map/geometries.ts`'s `resolveNodeCoordinates`. This component takes
// already-resolved coordinates as a prop and is agnostic to how a caller
// obtained them. A node this view cannot yet place still vanishes rather
// than dimming like a cross-filtered node elsewhere in the Glass — that
// distinct gap (absent vs. dimmed for an unplaceable node) remains open,
// named here so it is not mistaken for finished.
import bindMaplibreLayer from "@sigma/layer-maplibre";
import Graph from "graphology";
import maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  Map as MapLibreMap,
  RequestParameters,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol as PMTilesProtocol } from "pmtiles";
import Sigma from "sigma";
import { useEffect, useRef } from "react";

import type { GeoBin, PublicMapProvider } from "../../../../packages/schemas/generated";
import { SEQ_HEX } from "../color/tokens";
import type { WorkingSetGraph } from "../workingset/store";
import { resolveBundledStyle } from "./style";

const GEO_BINS_SOURCE_ID = "ospreyflow-geo-bins";
const GEO_BINS_LAYER_ID = "ospreyflow-geo-bins-heat";

function geoBinsFeatureCollection(geoBins: readonly GeoBin[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: geoBins.map((bin) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [bin.centroid_lon, bin.centroid_lat] },
      properties: { count: bin.count },
    })),
  };
}

type MapNodeAttributes = {
  x: number;
  y: number;
  lat: number;
  lng: number;
  size: number;
  label?: string;
};
type MapEdgeAttributes = Record<string, never>;

let pmtilesProtocolRegistered = false;

/** Idempotent — `MapView` may mount more than once per page lifetime
 * (switching away from and back to the Map view), but MapLibre's global
 * protocol registry must only ever gain one `pmtiles` handler. */
function ensurePmtilesProtocolRegistered(): void {
  if (pmtilesProtocolRegistered) return;
  const protocol = new PMTilesProtocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  pmtilesProtocolRegistered = true;
}

function buildMapGraph(
  graph: WorkingSetGraph,
  nodeCoordinates: ReadonlyMap<string, { lat: number; lng: number }>,
): Graph<MapNodeAttributes, MapEdgeAttributes> {
  const mapGraph = new Graph<MapNodeAttributes, MapEdgeAttributes>({
    multi: true,
    type: "mixed",
  });
  graph.forEachNode((nodeId) => {
    const coords = nodeCoordinates.get(nodeId);
    if (!coords) return;
    const node = graph.getNodeAttribute(nodeId, "data");
    const name = node.properties?.["name"];
    mapGraph.addNode(nodeId, {
      x: 0,
      y: 0, // overwritten by bindMaplibreLayer's own projection immediately after bind
      lat: coords.lat,
      lng: coords.lng,
      size: 6,
      label: typeof name === "string" ? name : undefined,
    });
  });
  // Only an edge whose *both* endpoints resolved a coordinate — an edge to
  // an absent node would be a dangling reference in `mapGraph`.
  graph.forEachEdge((edgeId, _attrs, source, target) => {
    if (
      mapGraph.hasNode(source) &&
      mapGraph.hasNode(target) &&
      !mapGraph.hasEdge(edgeId)
    ) {
      mapGraph.addEdgeWithKey(edgeId, source, target, {});
    }
  });
  return mapGraph;
}

export interface MapViewProps {
  /** The shared working set — read only. Never mutated by this component;
   * see the module docstring for why a local clone is rendered instead. */
  graph: WorkingSetGraph;
  provider: PublicMapProvider;
  nodeCoordinates: ReadonlyMap<string, { lat: number; lng: number }>;
  /** Attached to every request MapLibre makes to `apiBaseUrl` — currently
   * only the site-image proxy route (`site/api.ts`'s `siteImageUrl`)
   * needs this, since MapLibre's native `image` source has no other way
   * to carry a bearer token. Both optional: a caller with no site feature
   * mounted (or no `apiBaseUrl` to compare against) gets plain requests,
   * same as before this prop existed. */
  apiBaseUrl?: string;
  bearerToken?: string;
  /** Server-side-binned event density (`AnalyticsPort.geo_bins`,
   * `02_GLASS_FRONTEND.md` §3.5's "Heat map" row) — rendered as a native
   * MapLibre `heatmap` layer. Point clustering (Supercluster) for
   * individual un-binned markers is explicitly deferred past this
   * checkpoint (`07_BUILD_PLAN.md` Phase 5 Checkpoint 2 plan); nothing in
   * A1-A11 needs it. Defaults to empty so a caller with no cross-filter
   * wiring yet (an existing test harness) draws no heat layer. */
  geoBins?: readonly GeoBin[];
  /** Fired once the underlying `maplibregl.Map` exists, so a sibling
   * feature (`site/SiteCalibrationWizard.tsx`) can add its own
   * sources/layers directly — this component knows nothing about sites
   * itself, only that something else might want its map instance. */
  onMapReady?: (map: MapLibreMap) => void;
  /** Fired on a plotted node click — `08_ACCEPTANCE_SCENARIOS.md` A3's
   * "select the hotspot cells" mechanism: a grid-cell `Location` is a
   * plotted node here (`buildMapGraph`), so clicking it is how an analyst
   * actually performs A3's own step, per `App.tsx`'s wiring into
   * `crossfilter/store.ts`'s `selectedNodeIds`. */
  onNodeClick?: (nodeId: string) => void;
}

const EMPTY_GEO_BINS: readonly GeoBin[] = [];

export function MapView({
  graph,
  provider,
  nodeCoordinates,
  apiBaseUrl,
  bearerToken,
  geoBins = EMPTY_GEO_BINS,
  onMapReady,
  onNodeClick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  // Read inside the `load` handler below, which is registered once at map
  // creation and would otherwise close over whatever `geoBins` was at that
  // moment — a ref keeps it current without re-registering the handler
  // (which lives on the *other* effect, keyed on `[graph, provider, ...]`,
  // not on `geoBins`) every time new bins arrive.
  const geoBinsRef = useRef(geoBins);
  geoBinsRef.current = geoBins;
  // Same reasoning as `geoBinsRef` — `sigma.on("clickNode", ...)` is
  // registered once, in the mount effect below, and would otherwise close
  // over whichever `onNodeClick` App.tsx happened to pass on that render
  // (typically a fresh inline closure every render).
  const onNodeClickRef = useRef(onNodeClick);
  onNodeClickRef.current = onNodeClick;

  useEffect(() => {
    ensurePmtilesProtocolRegistered();
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    const mapGraph = buildMapGraph(graph, nodeCoordinates);
    const style = resolveBundledStyle(provider.style, provider, apiBaseUrl ?? "");
    const sigma = new Sigma<MapNodeAttributes, MapEdgeAttributes>(
      mapGraph,
      containerRef.current,
    );
    sigma.on("clickNode", ({ node }) => onNodeClickRef.current?.(node));

    // `attributionControl: false` is this checkpoint's mitigation for
    // CVE-2026-85061 (docs/06_DECISIONS.md, ADR-014 amendment) — MapLibre's
    // own control renders attribution HTML through the broken
    // `DOM.sanitize()` path; this component renders the same text itself,
    // below, as a plain (never `innerHTML`) node instead.
    //
    // `bindMaplibreLayer`'s own type declares its `sigma` parameter as the
    // library's default-generic `Sigma` (`Sigma<Attributes, Attributes,
    // Attributes>`), which TypeScript's invariant `Settings<N, E, G>` usage
    // makes it reject our more specific `Sigma<MapNodeAttributes,
    // MapEdgeAttributes>` for — a real generic-variance mismatch against a
    // third-party type, not a real runtime concern: the library only ever
    // reads `attrs.lat`/`attrs.lng` off nodes generically.
    // `transformRequest` attaches the bearer token to any request MapLibre
    // makes to this deployment's own API — currently only the site-image
    // proxy route (`site/api.ts`'s `siteImageUrl`), since that is the one
    // MapLibre-fetched resource this checkpoint puts behind auth. Inert
    // for the PMTiles basemap (fetched through the `pmtiles://` protocol
    // handler, never this callback) and for any future tier 3/4 provider
    // URL that doesn't happen to start with this deployment's own
    // `apiBaseUrl`.
    const transformRequest =
      apiBaseUrl && bearerToken
        ? (url: string): RequestParameters | undefined =>
            url.startsWith(apiBaseUrl)
              ? { url, headers: { Authorization: `Bearer ${bearerToken}` } }
              : undefined
        : undefined;

    const layer = bindMaplibreLayer(sigma as unknown as Sigma, {
      mapOptions: { style, attributionControl: false, transformRequest },
    });
    mapRef.current = layer.map;
    onMapReady?.(layer.map);

    // `load` fires once the style and its own sources have finished
    // loading — the documented point at which `addSource`/`addLayer` for
    // anything not already declared in the style spec is safe.
    layer.map.on("load", () => {
      if (layer.map.getSource(GEO_BINS_SOURCE_ID)) return;
      layer.map.addSource(GEO_BINS_SOURCE_ID, {
        type: "geojson",
        data: geoBinsFeatureCollection(geoBinsRef.current),
      });
      layer.map.addLayer({
        id: GEO_BINS_LAYER_ID,
        type: "heatmap",
        source: GEO_BINS_SOURCE_ID,
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "count"], 0, 0, 50, 1],
          "heatmap-intensity": 1,
          "heatmap-radius": 24,
          "heatmap-opacity": 0.75,
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(0,0,0,0)",
            0.2,
            SEQ_HEX[0],
            0.4,
            SEQ_HEX[1],
            0.6,
            SEQ_HEX[3],
            0.8,
            SEQ_HEX[4],
            1,
            SEQ_HEX[5],
          ],
        },
      });
    });

    return () => {
      mapRef.current = null;
      layer.clean();
      sigma.kill();
    };
  }, [graph, provider, nodeCoordinates, apiBaseUrl, bearerToken, onMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    const source = map?.getSource(GEO_BINS_SOURCE_ID) as GeoJSONSource | undefined;
    source?.setData(geoBinsFeatureCollection(geoBins));
  }, [geoBins]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <div
        style={{
          position: "absolute",
          bottom: 4,
          right: 8,
          fontSize: 11,
          color: "var(--text-secondary)",
          background: "rgba(0,0,0,0.4)",
          padding: "2px 6px",
          borderRadius: 2,
          pointerEvents: "none",
        }}
      >
        {provider.attribution}
        {provider.licence_note ? ` — ${provider.licence_note}` : ""}
      </div>
      {/* `00_ARCHITECTURE.md` §1.2: "the map UI should show a
          hosted-provider indicator whenever a tier 3 layer is live" —
          `client_scope !== "open"` covers tier 3 and any proxied non-open
          tier 4 profile alike. A tile-request pattern over a sensitive AOI
          is itself an intelligence leak independent of tile content (same
          section), so this is a standing analyst-facing caution, not a
          licensing footnote. */}
      {provider.client_scope !== "open" && (
        <div
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            fontSize: "var(--fs-11)",
            color: "var(--warning)",
            background: "var(--surface-panel)",
            border: "1px solid var(--warning)",
            borderRadius: "var(--r-chip)",
            padding: "2px 10px",
            pointerEvents: "none",
          }}
        >
          Hosted provider — {provider.client_scope}
        </div>
      )}
    </div>
  );
}
