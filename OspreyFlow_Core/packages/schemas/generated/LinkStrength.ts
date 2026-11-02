// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeId = string;
export type EdgeType = string;
export type BaseWeight = number;
export type Strength = number;
export type ParameterSet = string | null;
export type Heavy = number | null;
export type Fixed = number | null;
export type Occurrences = number;
export type LastSeen = string | null;
export type Id = string;
export type Label = string;
export type Change = "add" | "multiply" | "floor" | "exclude";
export type Size = number;
export type Layer = "file" | "installation" | "case";
export type RecordKind = string | null;
export type Applied = AppliedInfluencer[];

/**
 * A link's connection strength as its viewer may see it (decision 5), with what explains it
 * (decision 9): the stored weight, the rule and version it was computed under, what is heavy for
 * its type, and each influencer that changed it. Never a corpus-wide count (ADR-122).
 */
export interface LinkStrength {
  edge_id: EdgeId;
  edge_type: EdgeType;
  base_weight: BaseWeight;
  strength: Strength;
  parameter_set?: ParameterSet;
  heavy?: Heavy;
  fixed?: Fixed;
  occurrences?: Occurrences;
  last_seen?: LastSeen;
  applied?: Applied;
  [k: string]: unknown;
}
/**
 * One influencer that changed one link, and the kind of record that evidenced it (None for a
 * direct-links influencer). Only a record the viewer may see is ever named.
 */
export interface AppliedInfluencer {
  id: Id;
  label: Label;
  change: Change;
  size: Size;
  layer: Layer;
  record_kind?: RecordKind;
  [k: string]: unknown;
}
