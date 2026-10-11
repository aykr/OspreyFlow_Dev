// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type OspreyMark = "OspreyFlow";
export type InvestigationId = string;
export type PackId = string;
export type Version = number;
export type ExportedAt = string;
export type ExportedBy = string;
export type HandlingLevel = string;
export type RestsOnRetractedEvidence = boolean;

/**
 * ADR-047's mark for a pack: what a recipient must act on, printed on every page. A pack is
 * frozen snapshots, not a view of the graph, so it carries its version, not a resolution
 * threshold.
 */
export interface PackExportMark {
  osprey_mark?: OspreyMark;
  investigation_id: InvestigationId;
  pack_id: PackId;
  version: Version;
  exported_at: ExportedAt;
  exported_by: ExportedBy;
  handling_level: HandlingLevel;
  rests_on_retracted_evidence?: RestsOnRetractedEvidence;
  [k: string]: unknown;
}
