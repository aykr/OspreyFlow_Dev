// Pure edits to a pipeline graph (ADR-108 phase B). Each returns a new graph and never mutates;
// ids are minted unique within the graph; the save gate (`pipeline_rule_violations`, server-side)
// remains the authority on validity — these constructors just never break it by shape alone.
import type { PipelineEdge, PipelineGraph, PipelineNode } from "../../../../../packages/schemas/generated";

function nodesOf(graph: PipelineGraph): PipelineNode[] {
  return graph.nodes ?? [];
}

function edgesOf(graph: PipelineGraph): PipelineEdge[] {
  return graph.edges ?? [];
}

function mintId(graph: PipelineGraph, stem: string): string {
  const taken = new Set(nodesOf(graph).map((n) => n.id));
  for (let i = 1; ; i++) {
    const candidate = i === 1 ? stem : `${stem}-${i}`;
    if (!taken.has(candidate)) return candidate;
  }
}

/** A whole new branch — source → profile → map → load — wired to the domain root. */
export function addSourceChain(graph: PipelineGraph, label: string): PipelineGraph {
  const domain = nodesOf(graph).find((n) => n.kind === "domain_model");
  const source = mintId(graph, "source-b");
  const profile = `${source}-profile`;
  const map = `${source}-map`;
  const load = `${source}-load`;
  const nodes: PipelineNode[] = [
    ...nodesOf(graph),
    { id: source, kind: "source", label, config: {} },
    { id: profile, kind: "profile", label: "Profile", config: {} },
    { id: map, kind: "map", label: "Map", config: {} },
    { id: load, kind: "load", label: "Load", config: {} },
  ];
  const edges: PipelineEdge[] = [
    ...edgesOf(graph),
    ...(domain ? [{ source: domain.id, target: source }] : []),
    { source, target: profile },
    { source: profile, target: map },
    { source: map, target: load },
  ];
  return { nodes, edges };
}

/** An extract stage and its own load, fed by the named map (the save gate's placement rule). */
export function addExtractAfter(graph: PipelineGraph, mapId: string): PipelineGraph {
  const extract = mintId(graph, "extract");
  const load = `${extract}-load`;
  return {
    nodes: [
      ...nodesOf(graph),
      { id: extract, kind: "extract", label: "Extract", config: {} },
      { id: load, kind: "load", label: "Load", config: {} },
    ],
    edges: [
      ...edgesOf(graph),
      { source: mapId, target: extract },
      { source: extract, target: load },
    ],
  };
}

/** An enrich stage spliced after the named node, feeding a new load of its own. */
export function addEnrichAfter(graph: PipelineGraph, afterId: string): PipelineGraph {
  const enrich = mintId(graph, "enrich");
  const load = `${enrich}-load`;
  return {
    nodes: [
      ...nodesOf(graph),
      { id: enrich, kind: "enrich", label: "Enrich", config: {} },
      { id: load, kind: "load", label: "Load", config: {} },
    ],
    edges: [
      ...edgesOf(graph),
      { source: afterId, target: enrich },
      { source: enrich, target: load },
    ],
  };
}

export function removeNode(graph: PipelineGraph, nodeId: string): PipelineGraph {
  return {
    nodes: nodesOf(graph).filter((n) => n.id !== nodeId),
    edges: edgesOf(graph).filter((e) => e.source !== nodeId && e.target !== nodeId),
  };
}

export function connectNodes(graph: PipelineGraph, source: string, target: string): PipelineGraph {
  if (edgesOf(graph).some((e) => e.source === source && e.target === target)) return graph;
  return { nodes: nodesOf(graph), edges: [...edgesOf(graph), { source, target }] };
}

/** One node's config replaced, everything else untouched. */
export function withNodeConfig(
  graph: PipelineGraph,
  nodeId: string,
  config: Record<string, unknown>,
): PipelineGraph {
  return {
    nodes: nodesOf(graph).map((n) => (n.id === nodeId ? { ...n, config } : n)),
    edges: edgesOf(graph),
  };
}
