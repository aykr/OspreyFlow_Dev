// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Score = number;
export type MaxHops = number;
export type Decay = number;
export type WindowDays = number;
export type AsOf = string;
export type Name = string;
export type Hops = number;
export type AlertIds = string[];
export type Summaries = string[];
export type Contribution = number;
export type Contributions = RiskContribution[];

/**
 * *Neighbourhood risk* (ADR-109 phase E, ruling 9's defaults): the case's alerts within
 * `max_hops` of an entity, each decayed by `decay` per hop and counted for `window_days` —
 * computed at read, as the reader reads the graph, never stored, so it says only what their own
 * visible graph supports (rule 3).
 */
export interface NeighbourhoodRisk {
  node_id: NodeId;
  score: Score;
  max_hops: MaxHops;
  decay: Decay;
  window_days: WindowDays;
  as_of: AsOf;
  contributions?: Contributions;
  [k: string]: unknown;
}
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
