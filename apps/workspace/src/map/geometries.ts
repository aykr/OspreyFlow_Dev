// Resolving a working set's `Location` nodes to coordinates `MapView` can
// plot — `AnalyticsPort.get_geometries` (built Checkpoint 1), exposed over
// HTTP for the first time this checkpoint (`POST /v1/analytics/geometries`,
// `services/api/app.py`). Previously `App.tsx` fed `MapView` a hardcoded
// empty map (`MapView.tsx`'s own module docstring) since no read path
// existed yet.
import type { GeometryRecord, Node } from "../../../../packages/schemas/generated";
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
export function locationGeometryRefs(graph: WorkingSetGraph): Map<string, string> {
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
    if (record) coordinates.set(nodeId, { lat: record.lat, lng: record.lon });
  }
  return coordinates;
}
