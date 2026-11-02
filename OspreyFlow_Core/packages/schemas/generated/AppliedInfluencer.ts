// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type Change = "add" | "multiply" | "floor" | "exclude";
export type Size = number;
export type Layer = "file" | "installation" | "case";
export type RecordKind = string | null;

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
