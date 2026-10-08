// The MapLibre view — `spec/02_GLASS_FRONTEND.md` §3.5, ADR-014.
//
// **A separate Sigma instance over a local node clone, not the shared
// working-set graph.** `@sigma/layer-maplibre`'s `bindMaplibreLayer`
// mutates `x`/`y` on every node in whatever graph it is bound to
// (`updateGraphCoordinates`, confirmed by reading the package's real
// source, not assumed from its README) — sharing `GlassCanvas`'s
// graphology instance would have this view's geographic projection
// silently corrupt the Graph view's own layout the moment both had ever
// mounted. `spec/02_GLASS_FRONTEND.md` §2's "Graph · Map · Matrix ...
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
import { useEffect, useRef, useState } from "react";

import type {
  GeoBin,
  PublicMapProvider,
  Sighting,
} from "../../../../packages/schemas/generated";
import { SEQ_HEX } from "../color/tokens";
import type { WorkingSetGraph } from "../workingset/store";
import { BasemapUnavailableError, checkBasemapAvailable } from "./basemapAvailability";
import { conduitRequest } from "./conduitRequest";
import { registerAuthorisedPmtilesSource } from "./pmtilesAuth";
import { resolveBundledStyle, resolvePmtilesSourceUrl } from "./style";

const GEO_BINS_SOURCE_ID = "ospreyflow-geo-bins";
const GEO_BINS_LAYER_ID = "ospreyflow-geo-bins-heat";

// B18's own snail trail (`spec/02_GLASS_FRONTEND.md` §3.5, `08_
// ACCEPTANCE_SCENARIOS.md`) — two MapLibre layers over one source: the
// accumulated path so far (a `LineString`) and the current position (the
// most recent revealed sighting, a `Point`). Native MapLibre layers, not
// added to the Sigma `mapGraph` above — a sighting is a point-in-time
// observation, not a working-set node, and has no place in that graph.
const SNAIL_TRAIL_SOURCE_ID = "ospreyflow-snail-trail";
const SNAIL_TRAIL_LINE_LAYER_ID = "ospreyflow-snail-trail-line";
const SNAIL_TRAIL_POINT_LAYER_ID = "ospreyflow-snail-trail-point";

function snailTrailFeatureCollection(
  revealedSightings: readonly Sighting[],
): GeoJSON.FeatureCollection {
  const coordinates = revealedSightings.map((s) => [s.lon, s.lat]);
  const features: GeoJSON.Feature[] = [];
  if (coordinates.length >= 2) {
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates },
      properties: {},
    });
  }
  const current = coordinates.at(-1);
  if (current) {
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: current },
      properties: { current: true },
    });
  }
  return { type: "FeatureCollection", features };
}

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

let pmtilesProtocol: PMTilesProtocol | null = null;

/** Idempotent — `MapView` may mount more than once per page lifetime
 * (switching away from and back to the Map view), but MapLibre's global
 * protocol registry must only ever gain one `pmtiles` handler.
 *
 * The instance is kept rather than discarded now: authorised sources are
 * registered against it per provider (`pmtilesAuth.ts`), which is what
 * puts the bearer token on the basemap's own tile reads. */
function ensurePmtilesProtocolRegistered(): PMTilesProtocol {
  if (pmtilesProtocol) return pmtilesProtocol;
  const protocol = new PMTilesProtocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  pmtilesProtocol = protocol;
  return protocol;
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
   * individual un-binned markers is explicitly deferred to later work;
   * nothing in
   * A1-A11 needs it. Defaults to empty so a caller with no cross-filter
   * wiring yet (an existing test harness) draws no heat layer. */
  geoBins?: readonly GeoBin[];
  /** B18's own snail trail — sightings already filtered to "revealed so
   * far" by the caller's own playback fraction (`playback/math.ts`'s
   * `itemsUpTo`), not the full window's population; this component only
   * ever renders exactly what it is given. `undefined`/empty draws no
   * trail layer at all. */
  snailTrail?: readonly Sighting[];
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

const EMPTY_SIGHTINGS: readonly Sighting[] = [];

export function MapView({
  graph,
  provider,
  nodeCoordinates,
  apiBaseUrl,
  bearerToken,
  geoBins = EMPTY_GEO_BINS,
  snailTrail = EMPTY_SIGHTINGS,
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
  const snailTrailRef = useRef(snailTrail);
  snailTrailRef.current = snailTrail;
  // Same reasoning as `geoBinsRef` — `sigma.on("clickNode", ...)` is
  // registered once, in the mount effect below, and would otherwise close
  // over whichever `onNodeClick` App.tsx happened to pass on that render
  // (typically a fresh inline closure every render).
  const onNodeClickRef = useRef(onNodeClick);
  onNodeClickRef.current = onNodeClick;
  // Set by the mount effect below when `checkBasemapAvailable` 404s — Stage 3a's own rehearsal
  // finding, 23 September 2026: a missing local PMTiles build used to leave this view a silent
  // blank canvas rather than telling the operator what to do about it.
  const [basemapUnavailable, setBasemapUnavailable] = useState<string | null>(null);
  // Holds the real teardown for whichever mount actually ran — `mount()` below is async (the
  // basemap preflight check awaits a fetch), so the cleanup a synchronous effect body would
  // normally return can't yet reference the map/sigma instance it creates.
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    setBasemapUnavailable(null);
    let cancelled = false;

    async function mount(): Promise<void> {
      if (provider.kind === "vector" && provider.source) {
        const sourceUrl = resolvePmtilesSourceUrl(provider.source, apiBaseUrl ?? "");
        // Before the availability check, not after: the check can return early on a 404, and the
        // registration has to be in place for *this* provider's URL by the time the style below
        // asks MapLibre to open `pmtiles://<sourceUrl>`. Registering it here rather than in the
        // mount-once effect above is deliberate — the URL and the token are both per-provider
        // and per-session, and neither is known in an effect with an empty dependency list.
        registerAuthorisedPmtilesSource(
          ensurePmtilesProtocolRegistered(),
          sourceUrl,
          bearerToken,
        );
        try {
          await checkBasemapAvailable(sourceUrl, bearerToken);
        } catch (err) {
          if (err instanceof BasemapUnavailableError) {
            if (!cancelled) setBasemapUnavailable(err.message);
            return;
          }
          throw err;
        }
      }
      if (cancelled || !containerRef.current) return;

      const mapGraph = buildMapGraph(graph, nodeCoordinates);
      const style = resolveBundledStyle(provider.style, provider, apiBaseUrl ?? "");
      const sigma = new Sigma<MapNodeAttributes, MapEdgeAttributes>(
        mapGraph,
        containerRef.current,
      );
      sigma.on("clickNode", ({ node }) => onNodeClickRef.current?.(node));

      // `attributionControl: false` is this checkpoint's mitigation for
      // CVE-2026-85061 (spec/06_DECISIONS.md, ADR-014 amendment) — MapLibre's
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
      // handler, never this callback) and for any tier 3/4 provider's URL,
      // which is not under the Conduit's own `/v1/` (`conduitRequest.ts`).
      const transformRequest = bearerToken
        ? (url: string): RequestParameters | undefined =>
            conduitRequest(url, apiBaseUrl ?? "", bearerToken, window.location.origin)
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

        if (!layer.map.getSource(SNAIL_TRAIL_SOURCE_ID)) {
          layer.map.addSource(SNAIL_TRAIL_SOURCE_ID, {
            type: "geojson",
            data: snailTrailFeatureCollection(snailTrailRef.current),
          });
          layer.map.addLayer({
            id: SNAIL_TRAIL_LINE_LAYER_ID,
            type: "line",
            source: SNAIL_TRAIL_SOURCE_ID,
            filter: ["==", ["geometry-type"], "LineString"],
            // A sighting trail is data: the sequential ramp, not brass (ADR-097).
            paint: { "line-color": SEQ_HEX[4], "line-width": 2, "line-opacity": 0.85 },
          });
          layer.map.addLayer({
            id: SNAIL_TRAIL_POINT_LAYER_ID,
            type: "circle",
            source: SNAIL_TRAIL_SOURCE_ID,
            filter: ["==", ["geometry-type"], "Point"],
            paint: {
              "circle-color": SEQ_HEX[5],
              "circle-radius": 6,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.5,
            },
          });
        }
      });

      // ADR-086: a sash changes the map's box without a window resize; the observer tells both
      // the map and the graph layer drawn over it.
      const observer =
        typeof ResizeObserver === "function" && containerRef.current
          ? new ResizeObserver(() => {
              layer.map.resize();
              sigma.resize();
            })
          : null;
      if (containerRef.current) observer?.observe(containerRef.current);

      cleanupRef.current = () => {
        observer?.disconnect();
        mapRef.current = null;
        layer.clean();
        sigma.kill();
      };
    }

    void mount();

    return () => {
      cancelled = true;
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, [graph, provider, nodeCoordinates, apiBaseUrl, bearerToken, onMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    const source = map?.getSource(GEO_BINS_SOURCE_ID) as GeoJSONSource | undefined;
    source?.setData(geoBinsFeatureCollection(geoBins));
  }, [geoBins]);

  useEffect(() => {
    const map = mapRef.current;
    const source = map?.getSource(SNAIL_TRAIL_SOURCE_ID) as GeoJSONSource | undefined;
    source?.setData(snailTrailFeatureCollection(snailTrail));
  }, [snailTrail]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: "100%",
          display: basemapUnavailable ? "none" : undefined,
        }}
      />
      {/* Stage 3a's own rehearsal finding, 23 September 2026: a missing local PMTiles build
          used to leave this view a silent blank canvas — this names the gap instead, the same
          "tell the operator exactly what is missing" shape `services/api/config.py`'s
          fail-fast-on-missing-`OIDC_JWKS_URL` already establishes. */}
      {basemapUnavailable && (
        <div
          role="alert"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            padding: 24,
            textAlign: "center",
            color: "var(--text-primary)",
            background: "var(--surface-app)",
          }}
        >
          <strong style={{ color: "var(--warning)" }}>Basemap not built</strong>
          <span style={{ fontSize: "var(--fs-11)", color: "var(--text-secondary)" }}>
            {basemapUnavailable}
          </span>
        </div>
      )}
      {!basemapUnavailable && (
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
      )}
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
