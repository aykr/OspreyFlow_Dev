// The Map canvas's graph, brought in line with the row template in place. It once cleared the graph
// and added every node back on each change, and Sigma did not redraw nodes removed and re-added in one
// tick: an entity picked as a link's start vanished, with the one selected (9 October 2026). A node
// or link that stays is updated; only what the template no longer has is dropped.
import type Graph from "graphology";

import type { OntologySchema, RowTemplate } from "../../../../../packages/schemas/generated";
import type { Palette } from "../../color/palette";
import type { MapSelection } from "./MapCanvas";
import { mapCanvasColours, mapNodeColour } from "./mapCanvasColours";

export const NODE_SIZE = 14;

export function layoutPosition(index: number): { x: number; y: number } {
  // Left-to-right in creation order — matches §4's own mockup, which draws
  // the row template as a simple flow rather than a force-directed cluster.
  return { x: index * 220, y: (index % 2) * 90 };
}

export function syncTemplateGraph(
  graph: Graph,
  template: RowTemplate,
  ontology: OntologySchema,
  selection: MapSelection,
  linkFromRef: string | null,
  palette: Palette,
): void {
  const colours = mapCanvasColours(palette);
  const refs = new Set(template.entities.map((entity) => entity.ref));
  graph.forEachNode((key) => {
    if (!refs.has(key)) graph.dropNode(key);
  });
  template.entities.forEach((entity, index) => {
    const visual = ontology.entity_types.find((t) => t.name === entity.type);
    const { x, y } = layoutPosition(index);
    graph.mergeNode(entity.ref, {
      label: `${entity.ref} · ${entity.type}`,
      x,
      y,
      size: NODE_SIZE,
      color: mapNodeColour(
        { selected: selection?.kind === "entity" && selection.ref === entity.ref, linkFrom: linkFromRef === entity.ref, visual },
        palette,
      ),
    });
  });
  const edges = template.edges ?? [];
  const wanted = new Map<string, { from: string; to: string; index: number; type: string }>();
  edges.forEach((edge, index) => {
    if (graph.hasNode(edge.from) && graph.hasNode(edge.to)) {
      wanted.set(`edge-${index}`, { from: edge.from, to: edge.to, index, type: edge.type });
    }
  });
  graph.forEachEdge((key, _attributes, source, target) => {
    const next = wanted.get(key);
    if (!next || next.from !== source || next.to !== target) graph.dropEdge(key);
  });
  wanted.forEach((edge, key) => {
    const isSelected = selection?.kind === "edge" && selection.index === edge.index;
    const attributes = {
      label: edge.type,
      size: isSelected ? 4 : 2,
      color: isSelected ? palette.brass : colours.edge,
      templateIndex: edge.index,
    };
    if (graph.hasEdge(key)) graph.mergeEdgeAttributes(key, attributes);
    else graph.addEdgeWithKey(key, edge.from, edge.to, attributes);
  });
}
