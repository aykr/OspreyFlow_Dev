// Find connections (ADR-116): the case's connections route, and a found route put on the canvas.
//
// The Conduit answers the fewest degrees that connect two nodes, or the routes at a degree asked
// for, at most ten with "more" said when there are others (rule 2). A route is put on the canvas the
// way the Pathfinder puts a path there (ADR-033): what the canvas lacks is sent to the case's `/seed`,
// so it is part of the working set, not only drawn.
import type { Connections, Edge, Node, Path } from "../../../../packages/schemas/generated";
import type { WorkingSetDelta } from "../workingset/models";

export interface ConnectionsContext {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

/** What a route needs to know of the canvas. */
export interface CanvasContents {
  hasNode: (id: string) => boolean;
  hasEdge: (id: string) => boolean;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function degreesApart(degree: number): string {
  return `${plural(degree, "degree", "degrees")} apart`;
}

/** The heading of one degree's routes. Ten shown of more is said as such, never as all of them. */
export function routeCountWords({ degree, count, more }: { degree: number; count: number; more: boolean }): string {
  const at = `at ${plural(degree, "degree", "degrees")}`;
  if (count === 0) return `No routes ${at}`;
  if (more) return `${count} of more than ${count} routes ${at}`;
  return `${plural(count, "route", "routes")} ${at}`;
}

/** Each node of a route with its degree from From: From is 0, the next 1, and so on. */
export function degreeMarks(route: Path): Map<string, number> {
  return new Map(route.nodes.map((node, index) => [node.id, index]));
}

export function routeOnCanvas(route: Path, canvas: CanvasContents): boolean {
  return route.nodes.every((n) => canvas.hasNode(n.id)) && route.edges.every((e) => canvas.hasEdge(e.id));
}

function caseUrl(context: ConnectionsContext, tail: string): string {
  return `${context.apiBaseUrl}/v1/investigations/${encodeURIComponent(context.investigationId)}/${tail}`;
}

function headers(context: ConnectionsContext): HeadersInit {
  return { Authorization: `Bearer ${context.bearerToken}`, "Content-Type": "application/json" };
}

export async function findConnections(
  context: ConnectionsContext,
  source: string,
  target: string,
  degree?: number,
): Promise<Connections> {
  const body: Record<string, unknown> = { source, target };
  if (degree !== undefined) body.degree = degree;
  const response = await fetch(caseUrl(context, "connections"), {
    method: "POST",
    headers: headers(context),
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`The search for connections failed (${response.status}). Try again.`);
  return (await response.json()) as Connections;
}

/** Sends what the canvas lacks of `route` to the case's working set, and gives back the change to
 * draw; `null` when the route is already all there, so nothing is asked. */
export async function seedRoute(
  context: ConnectionsContext,
  route: Path,
  canvas: CanvasContents,
): Promise<WorkingSetDelta | null> {
  return seedElements(context, route.nodes, route.edges, canvas, "The route");
}

/** Sends what the canvas lacks of `nodes` and `edges` to the case's working set — each once — and
 * gives back the change to draw; `null` when all of it is there already. Also how Explore adds what
 * an analyst chose (ADR-100 Amendment 9), so the server's working set and the canvas's own counters
 * see it, rather than a local add neither does. */
export async function seedElements(
  context: ConnectionsContext,
  nodes: readonly Node[],
  edges: readonly Edge[],
  canvas: CanvasContents,
  what = "It",
): Promise<WorkingSetDelta | null> {
  const lackingNodes = [...new Map(nodes.filter((n) => !canvas.hasNode(n.id)).map((n) => [n.id, n])).values()];
  const lackingEdges = [...new Map(edges.filter((e) => !canvas.hasEdge(e.id)).map((e) => [e.id, e])).values()];
  if (lackingNodes.length === 0 && lackingEdges.length === 0) return null;
  const response = await fetch(caseUrl(context, "seed"), {
    method: "POST",
    headers: headers(context),
    body: JSON.stringify({ nodes: lackingNodes, edges: lackingEdges }),
  });
  if (!response.ok) throw new Error(`${what} could not be added to the canvas (${response.status}). Try again.`);
  const outcome = (await response.json()) as { delta: WorkingSetDelta };
  return outcome.delta;
}
