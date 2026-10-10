// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Score = number;
export type Hops = number;
export type Seed = number;
export type Contribution = number;
export type Contributions = PropagationContribution[];

export interface PropagationResult {
  target: NodeId;
  score: Score;
  contributions?: Contributions;
  [k: string]: unknown;
}
export interface PropagationContribution {
  node_id: NodeId;
  hops: Hops;
  seed: Seed;
  contribution: Contribution;
  [k: string]: unknown;
}
