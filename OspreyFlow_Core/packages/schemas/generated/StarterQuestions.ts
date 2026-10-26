// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Question = string;
export type Var = string;
export type EntityType = string | null;
export type NodeId = string | null;
export type Nodes = PatternNode[];
export type EdgeType = string;
export type FromVar = string;
export type ToVar = string;
export type Edges = PatternEdge[];
export type Limit = number;
export type Questions = StarterQuestion[];
export type Total = number;

/**
 * The first few that suit the case, and how many suit it in all (rule 2).
 */
export interface StarterQuestions {
  questions: Questions;
  total: Total;
  [k: string]: unknown;
}
/**
 * A query-builder pattern that suits the case's types (ADR-100 decision 8, Amendment 7), run
 * with one action.
 */
export interface StarterQuestion {
  id: Id;
  question: Question;
  pattern: PatternQuery;
  [k: string]: unknown;
}
/**
 * A bounded pattern description the Conduit compiles from a fixed set
 * of builders — never free-form Gremlin (ADR-003).
 */
export interface PatternQuery {
  nodes: Nodes;
  edges: Edges;
  limit?: Limit;
  [k: string]: unknown;
}
export interface PatternNode {
  var: Var;
  entity_type?: EntityType;
  node_id?: NodeId;
  where?: Where;
  [k: string]: unknown;
}
export interface Where {
  [k: string]: string;
}
export interface PatternEdge {
  edge_type: EdgeType;
  from_var: FromVar;
  to_var: ToVar;
  [k: string]: unknown;
}
