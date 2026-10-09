// 9 October 2026, the data engineer's journey: picking an entity as a link's start made it, and the
// selected entity, vanish from the Map canvas while an unchanged one stayed put; a reload drew them
// again. The canvas cleared its graph and added every node back on each change, and Sigma does not
// reliably redraw nodes removed and re-added in one tick. The graph is now brought in line in place:
// a node or link that stays is updated, never removed and added back.
import Graph from "graphology";
import { describe, expect, it } from "vitest";

import { paletteFor } from "../../color/palette";
import type { OntologySchema, RowTemplate } from "../../../../../packages/schemas/generated";
import { syncTemplateGraph } from "./mapGraphSync";

const ONTOLOGY = {
  version: 12,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle" },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "circle" },
  ],
  edge_types: [],
} as unknown as OntologySchema;
const PALETTE = paletteFor("light");

const TEMPLATE: RowTemplate = {
  entities: [
    { ref: "subscriber", pole_class: "person", type: "Person", on_match: "create", properties: {} },
    { ref: "phone", pole_class: "object", type: "Endpoint", on_match: "create", properties: {} },
  ],
  edges: [{ type: "USES", from: "subscriber", to: "phone", properties: {} }],
} as unknown as RowTemplate;

function watched(graph: Graph): string[] {
  const events: string[] = [];
  graph.on("cleared", () => events.push("cleared"));
  graph.on("edgesCleared", () => events.push("edgesCleared"));
  graph.on("nodeDropped", ({ key }) => events.push(`dropped ${key}`));
  graph.on("edgeDropped", ({ key }) => events.push(`dropped ${key}`));
  return events;
}

describe("syncTemplateGraph", () => {
  it("updates an entity in place when it becomes a link's start", () => {
    const graph = new Graph();
    syncTemplateGraph(graph, TEMPLATE, ONTOLOGY, null, null, PALETTE);
    const events = watched(graph);
    syncTemplateGraph(graph, TEMPLATE, ONTOLOGY, { kind: "entity", ref: "phone" }, "subscriber", PALETTE);
    expect(events).toEqual([]);
    expect(graph.getNodeAttribute("subscriber", "color")).toBe(PALETTE.textPrimary);
    expect(graph.getNodeAttribute("phone", "color")).toBe(PALETTE.brass);
    expect(graph.size).toBe(1);
  });

  it("drops what the template no longer has and adds what it gains", () => {
    const graph = new Graph();
    syncTemplateGraph(graph, TEMPLATE, ONTOLOGY, null, null, PALETTE);
    const events = watched(graph);
    const without = { ...TEMPLATE, entities: [TEMPLATE.entities[0]!], edges: [] } as RowTemplate;
    syncTemplateGraph(graph, without, ONTOLOGY, null, null, PALETTE);
    expect(events.sort()).toEqual(["dropped edge-0", "dropped phone"]);
    expect(graph.order).toBe(1);
    syncTemplateGraph(graph, TEMPLATE, ONTOLOGY, null, null, PALETTE);
    expect(graph.order).toBe(2);
    expect(graph.size).toBe(1);
    expect(graph.source("edge-0")).toBe("subscriber");
  });
});
