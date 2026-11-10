// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PipelineId = string;
export type ExportedVersion = number;
export type Label = string;
export type ConnectorProfile = string | null;
export type SourceLocation = string | null;
export type LegalBasis = string | null;
export type RowTemplate = {
  [k: string]: unknown;
} | null;
export type Deduplicate = {
  [k: string]: unknown;
} | null;
export type PackVersions = {
  [k: string]: number;
} | null;
export type Pipeline = {
  [k: string]: unknown;
} | null;

/**
 * One pipeline's file: its definition as it was published. No owner, publisher, schedule
 * owner, case, dataset id or run is in it; the load node's dataset is the receiving one.
 */
export interface ReleasedPipeline {
  pipeline_id: PipelineId;
  exported_version: ExportedVersion;
  label: Label;
  connector_profile?: ConnectorProfile;
  source_location?: SourceLocation;
  handling?: Handling;
  legal_basis?: LegalBasis;
  row_template?: RowTemplate;
  deduplicate?: Deduplicate;
  pack_versions?: PackVersions;
  pipeline?: Pipeline;
}
export interface Handling {
  [k: string]: unknown;
}
