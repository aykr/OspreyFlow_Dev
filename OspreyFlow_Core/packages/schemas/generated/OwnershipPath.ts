// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeId = string;
export type LinkIds = EdgeId[];
export type Kind = "ownership" | "unknown" | "control";
export type Share = number | null;

/**
 * One chain from an owner to the target, its links in order. `ownership`: every link owns
 * with a stated percentage, and `share` is their product (as a percentage). `unknown`: a link
 * states no percentage, so the share is not known. `control`: a link controls rather than owns,
 * so the chain confers control, not a share.
 */
export interface OwnershipPath {
  link_ids: LinkIds;
  kind: Kind;
  share?: Share;
  [k: string]: unknown;
}
