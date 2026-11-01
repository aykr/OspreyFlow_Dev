// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Name = string;
export type EntityType = string;
export type Words = string;

/**
 * One alert the rule would have raised: the subject as the author reads it, and the finding.
 */
export interface PreviewExample {
  node_id: NodeId;
  name: Name;
  entity_type: EntityType;
  words: Words;
  [k: string]: unknown;
}
