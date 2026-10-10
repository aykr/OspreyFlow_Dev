// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Library = string;
export type Output = string;
export type DocumentsRead = number;
export type CandidatesQueued = number;
export type NodesWrittenInferred = number;
export type HandlingOverridden = number;
export type OverrideReason = string | null;
export type Refusals = string[];

/**
 * One extract node's run, loud about everything it did and refused (rules 2 and 5): how many
 * documents it read, where its findings went, how many carried an overridden handling, and every
 * refusal in words — a stage that could not run says so here, never silently does nothing.
 */
export interface ExtractStageReport {
  node_id: NodeId;
  library: Library;
  output: Output;
  documents_read?: DocumentsRead;
  candidates_queued?: CandidatesQueued;
  nodes_written_inferred?: NodesWrittenInferred;
  handling_overridden?: HandlingOverridden;
  override_reason?: OverrideReason;
  refusals?: Refusals;
  [k: string]: unknown;
}
