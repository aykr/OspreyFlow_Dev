// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * How many nodes of each entity type, and links of each link type, the principal can see. A
 * link counts only when both its ends can be seen, the same rule a degree follows.
 */
export interface TypeCounts {
  nodes?: Nodes;
  edges?: Edges;
  [k: string]: unknown;
}
export interface Nodes {
  [k: string]: number;
}
export interface Edges {
  [k: string]: number;
}
