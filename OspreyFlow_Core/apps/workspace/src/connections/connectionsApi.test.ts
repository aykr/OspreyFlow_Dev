import { afterEach, describe, expect, it, vi } from "vitest";

import type { Edge, Node, Path } from "../../../../packages/schemas/generated";
import {
  degreeMarks,
  degreesApart,
  findConnections,
  routeCountWords,
  routeOnCanvas,
  seedElements,
  seedRoute,
} from "./connectionsApi";

const node = (id: string) => ({ id, type: "Person", properties: {} }) as unknown as Node;
const edge = (source: string, target: string) =>
  ({ id: `${source}-${target}`, type: "ASSOCIATE_OF", source, target }) as unknown as Edge;
const route = (...ids: string[]): Path => ({
  nodes: ids.map(node),
  edges: ids.slice(1).map((id, i) => edge(ids[i]!, id)),
  length: ids.length - 1,
});
const CONTEXT = { apiBaseUrl: "http://api", bearerToken: "t", investigationId: "inv 1" };

afterEach(() => vi.unstubAllGlobals());

describe("the words for a degree and its routes (ADR-116)", () => {
  it("says how many degrees apart, with one degree singular", () => {
    expect(degreesApart(3)).toBe("3 degrees apart");
    expect(degreesApart(1)).toBe("1 degree apart");
  });

  it("counts the routes at a degree, and never presents a cut list as all of them (rule 2)", () => {
    expect(routeCountWords({ degree: 3, count: 2, more: false })).toBe("2 routes at 3 degrees");
    expect(routeCountWords({ degree: 1, count: 1, more: false })).toBe("1 route at 1 degree");
    expect(routeCountWords({ degree: 4, count: 10, more: true })).toBe("10 of more than 10 routes at 4 degrees");
    expect(routeCountWords({ degree: 5, count: 0, more: false })).toBe("No routes at 5 degrees");
  });
});

describe("a route on the canvas", () => {
  it("marks each node with its degree from From", () => {
    expect([...degreeMarks(route("a", "b", "c"))]).toEqual([["a", 0], ["b", 1], ["c", 2]]);
  });

  it("is on the canvas only when every node and link of it is", () => {
    const has = new Set(["a", "b", "c", "a-b", "b-c"]);
    const graph = { hasNode: (id: string) => has.has(id), hasEdge: (id: string) => has.has(id) };
    expect(routeOnCanvas(route("a", "b", "c"), graph)).toBe(true);
    has.delete("b-c");
    expect(routeOnCanvas(route("a", "b", "c"), graph)).toBe(false);
  });

  it("seeds only what the canvas lacks, through the case's seed route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ delta: { op: "add" } })));
    vi.stubGlobal("fetch", fetchMock);
    const has = new Set(["a", "a-b"]);
    const graph = { hasNode: (id: string) => has.has(id), hasEdge: (id: string) => has.has(id) };
    const delta = await seedRoute(CONTEXT, route("a", "b", "c"), graph);
    expect(delta).toEqual({ op: "add" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api/v1/investigations/inv%201/seed");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.nodes.map((n: Node) => n.id)).toEqual(["b", "c"]);
    expect(body.edges.map((e: Edge) => e.id)).toEqual(["b-c"]);
  });

  it("asks nothing when the route is already on the canvas", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const graph = { hasNode: () => true, hasEdge: () => true };
    expect(await seedRoute(CONTEXT, route("a", "b"), graph)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("findConnections", () => {
  it("asks the case's connections route, with a degree only when one is given", async () => {
    const answer = { degree: 2, paths: [], more: false, searched_to: 2 };
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(answer)));
    vi.stubGlobal("fetch", fetchMock);
    expect(await findConnections(CONTEXT, "a", "b")).toEqual(answer);
    await findConnections(CONTEXT, "a", "b", 4);
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string));
    expect(bodies).toEqual([{ source: "a", target: "b" }, { source: "a", target: "b", degree: 4 }]);
    expect(fetchMock.mock.calls[0]![0]).toBe("http://api/v1/investigations/inv%201/connections");
  });

  it("refuses in words when the search does not complete", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 503 })));
    await expect(findConnections(CONTEXT, "a", "b")).rejects.toThrow("The search for connections failed (503). Try again.");
  });
});

// Explore's adds (ADR-100 Amendment 9) go through the same seed: a node with its busiest links names
// each shared end once, and an answer the Conduit refuses is said, not drawn.
describe("seedElements", () => {
  it("sends each node and link once, and only what the canvas lacks", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ delta: { op: "add" } })));
    vi.stubGlobal("fetch", fetchMock);
    const has = new Set(["c"]);
    const graph = { hasNode: (id: string) => has.has(id), hasEdge: (id: string) => has.has(id) };
    await seedElements(CONTEXT, [node("a"), node("b"), node("a"), node("c")], [edge("a", "b"), edge("a", "b")], graph);
    const body = JSON.parse((fetchMock.mock.calls[0]![1] as RequestInit).body as string);
    expect(body.nodes.map((n: Node) => n.id)).toEqual(["a", "b"]);
    expect(body.edges.map((e: Edge) => e.id)).toEqual(["a-b"]);
  });

  it("says when the Conduit refuses, rather than drawing anything", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 409 })));
    const graph = { hasNode: () => false, hasEdge: () => false };
    await expect(seedElements(CONTEXT, [node("a")], [], graph)).rejects.toThrow(
      "It could not be added to the canvas (409). Try again.",
    );
  });
});
