// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
/**
 * The pipeline graph's closed node vocabulary (`06_DECISIONS.md` ADR-108). Closed on
 * purpose: rule 8 — no expression or scripting language in the Studio; every node is a declared
 * stage whose transforms remain Knowledge Adapters with golden files.
 */
export type PipelineNodeKind = "domain_model" | "source" | "profile" | "map" | "extract" | "enrich" | "load";
export type Label = string;
export type Nodes = PipelineNode[];
export type Source = string;
export type Target = string;
export type Edges = PipelineEdge[];

/**
 * ADR-108: the recipe as a typed DAG. A v1 recipe that has none is read as its canonical
 * chain (`pipeline_from_recipe`), derived at read time and never stored back.
 */
export interface PipelineGraph {
  nodes?: Nodes;
  edges?: Edges;
  [k: string]: unknown;
}
/**
 * One stage of a pipeline. `config` carries the stage's own settings (a source node's
 * connector profile and location, a domain node's pack) — its keys are each stage's declared
 * vocabulary, validated by `services/ingest/pipeline.py`, never free code.
 */
export interface PipelineNode {
  id: Id;
  kind: PipelineNodeKind;
  label: Label;
  config?: Config;
  [k: string]: unknown;
}
export interface Config {
  [k: string]: unknown;
}
/**
 * A data dependency: `source` feeds `target`. The graph is acyclic (validated at save).
 */
export interface PipelineEdge {
  source: Source;
  target: Target;
  [k: string]: unknown;
}
