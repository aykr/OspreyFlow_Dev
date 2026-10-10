// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Name = string;
export type Hops = number;
export type AlertIds = string[];
export type Summaries = string[];
export type Contribution = number;

/**
 * One alerted entity near the target and what it contributes: its alerts, how many hops
 * away, and its weight after decay.
 */
export interface RiskContribution {
  node_id: NodeId;
  name: Name;
  hops: Hops;
  alert_ids?: AlertIds;
  summaries?: Summaries;
  contribution: Contribution;
  [k: string]: unknown;
}
