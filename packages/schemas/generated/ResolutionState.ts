// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type ClusterId = string;
export type ClusterScore = number | null;
export type ResolutionRun = string | null;
export type NodeId = string;
export type ManuallyLinked = NodeId[];
export type ManuallySplit = NodeId[];

export interface ResolutionState {
  cluster_id?: ClusterId | null;
  cluster_score?: ClusterScore;
  resolution_run?: ResolutionRun;
  manually_linked?: ManuallyLinked;
  manually_split?: ManuallySplit;
  [k: string]: unknown;
}
