// A pipeline's staging steps as nodes of its graph (ADR-140 Amendment 12, Q1 (a)): each step a node
// whose config is its record (`schemas/staging.py`, less its id and kind), and the graph's lines kept
// to what the steps read, as `services/ingest/pipeline.pipeline_with_staging` draws them: a line from
// each table a step reads, and from the last step to Map, which no source then feeds directly. The
// save gate (`staging_gate`, server-side) stays the authority on validity; these edits never break
// it by shape alone. Pure: each returns a new graph.
import type { PipelineEdge, PipelineGraph, PipelineNode } from "../../../../../packages/schemas/generated";

/** The closed catalogue (rule 8): guided mode offers these and no other. */
export const STAGING_KINDS = ["lookup", "join", "filter", "derive", "union", "dedupe"] as const;
export type StagingKind = (typeof STAGING_KINDS)[number];

export const STAGING_KIND_NAMES: Record<StagingKind, string> = {
  lookup: "Lookup",
  join: "Join",
  filter: "Filter",
  derive: "Derive",
  union: "Union",
  dedupe: "Dedupe",
};

/** Derive's catalogue (`knowledge_adapters.derive.DERIVE_OPERATIONS`). */
export const DERIVE_OPERATIONS = ["concat", "split", "substring", "date_parse", "arithmetic", "case_when", "normalise"] as const;

export function isStagingStep(node: Pick<PipelineNode, "kind">): boolean {
  return (STAGING_KINDS as readonly string[]).includes(node.kind);
}

const text = (v: unknown): string => (typeof v === "string" ? v : "");

/** The tables a step reads, in order, as its record names them (`schemas.staging.step_inputs`). */
export function stepInputs(node: PipelineNode): string[] {
  const c = node.config ?? {};
  if (node.kind === "join") return [text(c.left), text(c.right)].filter(Boolean);
  if (node.kind === "union") return (Array.isArray(c.inputs) ? c.inputs : []).map(text).filter(Boolean);
  return [text(c.input)].filter(Boolean);
}

const nodesOf = (g: PipelineGraph) => g.nodes ?? [];
const edgesOf = (g: PipelineGraph) => g.edges ?? [];

/** A step's id is how later steps and the recipe read it: lower case, digits and underscores. */
function mintStepId(graph: PipelineGraph, kind: StagingKind): string {
  const taken = new Set(nodesOf(graph).map((n) => n.id));
  for (let i = 1; ; i++) {
    const id = i === 1 ? kind : `${kind}_${i}`;
    if (!taken.has(id)) return id;
  }
}

/** The steps that read `id`, directly or through other steps. */
function downstreamOf(graph: PipelineGraph, id: string): Set<string> {
  const steps = nodesOf(graph).filter(isStagingStep);
  const found = new Set<string>();
  let grew = true;
  while (grew) {
    grew = false;
    for (const s of steps) {
      if (found.has(s.id)) continue;
      if (stepInputs(s).some((t) => t === id || found.has(t))) {
        found.add(s.id);
        grew = true;
      }
    }
  }
  return found;
}

/** The tables a step may read: the pipeline's sources and every other step not fed by it. */
export function tablesFor(graph: PipelineGraph, stepId: string): string[] {
  const after = downstreamOf(graph, stepId);
  return nodesOf(graph)
    .filter((n) => n.id !== stepId && (n.kind === "source" || (isStagingStep(n) && !after.has(n.id))))
    .map((n) => n.id);
}

/** The steps no other step reads: the last one is the table Map reads. */
function terminalSteps(graph: PipelineGraph): PipelineNode[] {
  const steps = nodesOf(graph).filter(isStagingStep);
  const read = new Set(steps.flatMap(stepInputs));
  return steps.filter((s) => !read.has(s.id));
}

/** The table Map reads in a staged pipeline: the step no other step reads (the first such, where
 * the save gate would refuse more than one). `null` for a pipeline with no step. */
export function lastStagingStep(graph: PipelineGraph): string | null {
  return terminalSteps(graph)[0]?.id ?? null;
}

/** The graph's lines redrawn to what its steps read (see the head of this file). */
export function rewireStaging(graph: PipelineGraph): PipelineGraph {
  const nodes = nodesOf(graph);
  const ids = new Set(nodes.map((n) => n.id));
  const kinds = new Map(nodes.map((n) => [n.id, n.kind]));
  const steps = nodes.filter(isStagingStep);
  const maps = nodes.filter((n) => n.kind === "map").map((n) => n.id);
  const stepIds = new Set(steps.map((s) => s.id));
  let edges: PipelineEdge[] = edgesOf(graph).filter((e) => !stepIds.has(e.target));
  if (steps.length > 0) {
    edges = edges.filter((e) => !(maps.includes(e.target) && ["source", "profile", ...STAGING_KINDS].includes(kinds.get(e.source) ?? "")));
    for (const step of steps)
      for (const table of stepInputs(step)) if (ids.has(table)) edges.push({ source: table, target: step.id });
    for (const last of terminalSteps(graph)) for (const map of maps) edges.push({ source: last.id, target: map });
  } else {
    for (const map of maps)
      if (!edges.some((e) => e.target === map))
        for (const source of nodes.filter((n) => n.kind === "source")) edges.push({ source: source.id, target: map });
  }
  const seen = new Set<string>();
  edges = edges.filter((e) => {
    const key = `${e.source}\u0000${e.target}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return { nodes, edges };
}

/** A new step's record with what it reads filled in and everything else for its drawer to set. */
function emptyRecord(kind: StagingKind, input: string): Record<string, unknown> {
  switch (kind) {
    case "lookup":
      return { input, list: "", on: "", add: [] };
    case "join":
      return { left: input, right: "", left_key: "", right_key: "", how: "inner", add: [] };
    case "filter":
      return { input, keep: [] };
    case "derive":
      return { input, column: "", operation: "concat", columns: [], settings: {} };
    case "union":
      return { inputs: [input] };
    case "dedupe":
      return { input, on: [] };
  }
}

/** A step of `kind`, reading `afterId` when that is a source or a step, else the last step or the
 * first source; Map then reads the new last step. */
export function addStagingStep(graph: PipelineGraph, kind: StagingKind, afterId: string | null): { graph: PipelineGraph; id: string } {
  const nodes = nodesOf(graph);
  const after = nodes.find((n) => n.id === afterId);
  const input =
    after && (after.kind === "source" || isStagingStep(after))
      ? after.id
      : (terminalSteps(graph)[0]?.id ?? nodes.find((n) => n.kind === "source")?.id ?? "");
  const id = mintStepId(graph, kind);
  const node: PipelineNode = { id, kind: kind as PipelineNode["kind"], label: STAGING_KIND_NAMES[kind], config: emptyRecord(kind, input) };
  return { graph: rewireStaging({ nodes: [...nodes, node], edges: edgesOf(graph) }), id };
}

/** One step's record replaced and the lines redrawn to what it now reads. */
export function withStepRecord(graph: PipelineGraph, stepId: string, config: Record<string, unknown>, label?: string): PipelineGraph {
  return rewireStaging({
    nodes: nodesOf(graph).map((n) => (n.id === stepId ? { ...n, config, ...(label ? { label } : {}) } : n)),
    edges: edgesOf(graph),
  });
}

/** A step removed, and the lines redrawn (a step that read it then reads nothing, which the save
 * gate names). */
export function removeStagingStep(graph: PipelineGraph, stepId: string): PipelineGraph {
  return rewireStaging({
    nodes: nodesOf(graph).filter((n) => n.id !== stepId),
    edges: edgesOf(graph).filter((e) => e.source !== stepId && e.target !== stepId),
  });
}
