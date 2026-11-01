// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Days = number;
export type WouldRaise = number;
/**
 * @maxItems 5
 */
export type Examples =
  | []
  | [PreviewExample]
  | [PreviewExample, PreviewExample]
  | [PreviewExample, PreviewExample, PreviewExample]
  | [PreviewExample, PreviewExample, PreviewExample, PreviewExample]
  | [PreviewExample, PreviewExample, PreviewExample, PreviewExample, PreviewExample];
export type NodeId = string;
export type Name = string;
export type EntityType = string;
export type Words = string;
export type Words1 = string;

/**
 * ADR-133 decision 3: what the rule would have raised over the last `days` days, run as its
 * author over stored data, raising and writing nothing. `would_raise` and `examples` are counted
 * only over what the author may see (rules 3 and 7). Over the working-set limit the preview is
 * refused with `limit_exceeded` instead, never counted in part (rule 2).
 */
export interface RulePreview {
  days?: Days;
  would_raise: WouldRaise;
  examples?: Examples;
  words: Words1;
  [k: string]: unknown;
}
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
