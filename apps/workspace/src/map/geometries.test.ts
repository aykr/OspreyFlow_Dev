import Graph from "graphology";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import * as api from "../analytics/api";
import type { WorkingSetGraph, WorkingSetNodeAttributes } from "../workingset/store";
import { locationGeometryRefs, resolveNodeCoordinates } from "./geometries";

function node(type: string, properties: Record<string, unknown> = {}): Node {
  return {
    id: "unused",
    type,
    properties,
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: {
      classification: "OFFICIAL",
      handling_code: "NONE",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "tester" },
  };
}

function buildGraph(entries: Array<[string, WorkingSetNodeAttributes]>): WorkingSetGraph {
  const graph: WorkingSetGraph = new Graph({ multi: true, type: "mixed" });
  for (const [id, attrs] of entries) graph.addNode(id, attrs);
  return graph;
}

describe("locationGeometryRefs", () => {
  it("collects only Location nodes carrying a geometry_ref", () => {
    const graph = buildGraph([
      ["loc-1", { data: node("Location", { geometry_ref: "geo-abc" }) }],
      ["loc-2", { data: node("Location", {}) }],
      ["person-1", { data: node("Person", { geometry_ref: "geo-xyz" }) }],
    ]);
    expect(locationGeometryRefs(graph)).toEqual(new Map([["loc-1", "geo-abc"]]));
  });
});

describe("resolveNodeCoordinates", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns an empty map without calling the API when there are no Location nodes", async () => {
    const spy = vi.spyOn(api, "fetchGeometries");
    const graph = buildGraph([["person-1", { data: node("Person") }]]);

    const coordinates = await resolveNodeCoordinates("http://api", "token", graph);

    expect(spy).not.toHaveBeenCalled();
    expect(coordinates.size).toBe(0);
  });

  it("resolves each Location node's geometry_ref to its record's lat/lon", async () => {
    vi.spyOn(api, "fetchGeometries").mockResolvedValue([
      {
        geometry_ref: "geo-abc",
        version: 1,
        lon: -1.5,
        lat: 53.8,
        source_crs: "EPSG:4326",
        handling: {
          classification: "OFFICIAL",
          handling_code: "NONE",
          originator: "unit-1",
          owning_unit: "unit-1",
        },
      },
    ]);
    const graph = buildGraph([
      ["loc-1", { data: node("Location", { geometry_ref: "geo-abc" }) }],
      ["loc-2", { data: node("Location", { geometry_ref: "geo-missing" }) }],
    ]);

    const coordinates = await resolveNodeCoordinates("http://api", "token", graph);

    expect(coordinates).toEqual(new Map([["loc-1", { lat: 53.8, lng: -1.5 }]]));
  });
});
