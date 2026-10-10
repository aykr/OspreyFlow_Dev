// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Threshold = number;
export type NodeType = string;
export type CumulativePercent = number;
export type ShareUnknown = boolean;
export type Controls = boolean;
export type EdgeId = string;
export type LinkIds = EdgeId[];
export type Kind = "ownership" | "unknown" | "control";
export type Share = number | null;
export type Paths = OwnershipPath[];
export type BeneficialOwner = boolean;
export type PossibleBeneficialOwner = boolean;
export type Owners = OwnerTrace[];
export type Cycles = NodeId[][];

export interface OwnershipTrace {
  target: NodeId;
  threshold: Threshold;
  owners?: Owners;
  cycles?: Cycles;
  [k: string]: unknown;
}
export interface OwnerTrace {
  node_id: NodeId;
  node_type: NodeType;
  cumulative_percent: CumulativePercent;
  share_unknown?: ShareUnknown;
  controls?: Controls;
  paths?: Paths;
  beneficial_owner?: BeneficialOwner;
  possible_beneficial_owner?: PossibleBeneficialOwner;
  [k: string]: unknown;
}
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
