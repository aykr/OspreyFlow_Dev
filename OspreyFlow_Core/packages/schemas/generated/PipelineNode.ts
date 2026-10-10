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
