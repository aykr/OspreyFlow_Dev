// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py and _pending_port_placeholders.py, via generate_ts.py
export type NodeId = string;
export type Degree = number;

export interface NeighbourhoodStats {
  node_id: NodeId;
  degree: Degree;
  degree_by_type?: DegreeByType;
  [k: string]: unknown;
}
export interface DegreeByType {
  [k: string]: number;
}
