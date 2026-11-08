// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationId = string;
export type Action = "merge" | "delete";
export type Items = number;
export type Links = number;
export type SizeBytes = number;
export type Would = string;

/**
 * A removed case's *Merge into the dataset* or *Delete*, run dry: what it would touch, in
 * counts, and nothing written. The action itself is the promotion's (L3.4).
 */
export interface LayerDryRun {
  investigation_id: InvestigationId;
  action: Action;
  items: Items;
  links: Links;
  size_bytes: SizeBytes;
  would: Would;
}
