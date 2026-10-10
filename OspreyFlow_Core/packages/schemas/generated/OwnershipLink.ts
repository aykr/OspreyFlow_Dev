// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeId = string;
export type NodeId = string;
export type Kind = "owns" | "controls";
export type Percent = number | null;

/**
 * One link of a corporate structure, owner to owned: `owns` with its percentage (0–100;
 * `None` when the record states none), or `controls` (control without a stated share).
 */
export interface OwnershipLink {
  id: EdgeId;
  source: NodeId;
  target: NodeId;
  kind: Kind;
  percent?: Percent;
  [k: string]: unknown;
}
