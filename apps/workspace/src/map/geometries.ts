// Resolving a working set's `Location` nodes to coordinates `MapView` can
// plot — `AnalyticsPort.get_geometries` (built Checkpoint 1), exposed over
// HTTP for the first time this checkpoint (`POST /v1/analytics/geometries`,
// `services/api/app.py`). Previously `App.tsx` fed `MapView` a hardcoded
// empty map (`MapView.tsx`'s own module docstring) since no read path
// existed yet.
import type {
  GeometryRecord,
  Node,
} from "../../../../packages/schemas/generated";
import { fetchGeometries } from "../analytics/api";
import type { WorkingSetGraph } from "../workingset/store";

/** `node.properties.geometry_ref` is untyped JSON on the wire
 * (`Node.ts`'s `Properties` is an index signature) — narrowed here once,
 * rather than at every call site. */
function geometryRefOf(node: Node): string | null {
  const ref = node.properties?.["geometry_ref"];
  return typeof ref === "string" ? ref : null;
}

/** Every working-set `Location` node with a `geometry_ref`, keyed by node
 * id — a `Location` with none (a jurisdiction/boundary with no single
 * point, per `packages/ontology/default.yaml`'s own comment) is simply
 * absent from the result, same as one this partition has no row for. */
export function locationGeometryRefs(
  graph: WorkingSetGraph,
): Map<string, string> {
  const refs = new Map<string, string>();
  graph.forEachNode((nodeId, attrs) => {
    const node = attrs.data;
    if (node.type !== "Location") return;
    const ref = geometryRefOf(node);
    if (ref) refs.set(nodeId, ref);
  });
  return refs;
}

/** Resolves every working-set `Location` node's `geometry_ref` to a
 * plottable coordinate in one round trip. Only nodes with a *resolvable*
 * geometry_ref appear in the result — `MapView`'s own module docstring:
 * "only nodes with a resolved coordinate are plotted, the rest are
 * absent, not dimmed." */
export async function resolveNodeCoordinates(
  apiBaseUrl: string,
  bearerToken: string,
  graph: WorkingSetGraph,
): Promise<Map<string, { lat: number; lng: number }>> {
  const refsByNode = locationGeometryRefs(graph);
  const coordinates = new Map<string, { lat: number; lng: number }>();
  if (refsByNode.size === 0) return coordinates;

  const uniqueRefs = [...new Set(refsByNode.values())];
  const records = await fetchGeometries(apiBaseUrl, bearerToken, uniqueRefs);
  const recordByRef = new Map<string, GeometryRecord>(
    records.map((record) => [record.geometry_ref, record]),
  );
  for (const [nodeId, ref] of refsByNode) {
    const record = recordByRef.get(ref);
    if (record && record.lat != null && record.lon != null) {
      coordinates.set(nodeId, { lat: record.lat, lng: record.lon });
      continue;
    }
    // **A site-grid cell is a `POLYGON` (owner ruling R9, round 13cf)**, so it carries no
    // `lat`/`lon`. It is drawn at its derived centroid, the mean of its ring's corners. Before
    // R9 a polygon record was simply absent here, and every cell would have vanished from the map
    // the moment cells became polygons.
    const centroid = record?.geometry_wkb
      ? polygonCentroid(record.geometry_wkb)
      : null;
    if (centroid) coordinates.set(nodeId, centroid);
  }
  return coordinates;
}

/** The mean of a WKB polygon's outer-ring corners, or `null` for anything that is not a
 * well-formed little-endian polygon. `geometry_wkb` is base64 on the wire (`GeometryRecord`,
 * round 13cf). The closing point, which repeats the first, is not counted twice.
 * `packages/geo/wkb.py` writes this layout and `ring_centroid` there is the same arithmetic. */
export function polygonCentroid(
  wkbBase64: string,
): { lat: number; lng: number } | null {
  let bytes: Uint8Array;
  try {
    // Pydantic's `base64` JSON mode is the URL-safe alphabet (`-`, `_`), which `atob` refuses,
    // so it is mapped back to the standard alphabet and re-padded first.
    const standard = wkbBase64.replace(/-/g, "+").replace(/_/g, "/");
    const padded = standard + "=".repeat((4 - (standard.length % 4)) % 4);
    bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
  if (bytes.length < 13) return null;
  const view = new DataView(bytes.buffer);
  if (view.getUint8(0) !== 1 || view.getUint32(1, true) !== 3) return null;
  if (view.getUint32(5, true) < 1) return null;
  const points = view.getUint32(9, true);
  if (points < 4 || bytes.length < 13 + points * 16) return null;
  let lng = 0;
  let lat = 0;
  const corners = points - 1;
  for (let i = 0; i < corners; i += 1) {
    lng += view.getFloat64(13 + i * 16, true);
    lat += view.getFloat64(13 + i * 16 + 8, true);
  }
  return { lat: lat / corners, lng: lng / corners };
}
