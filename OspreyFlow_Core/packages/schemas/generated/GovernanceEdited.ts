// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type DatasetId = string;
export type ConnectionId = string;
export type Name = string;
export type Location = string;
export type ConnectorProfile = string;
export type LegalBasis = string | null;
export type Trigger = "manual" | "watch";
export type Pattern = string | null;
export type Mode = "snapshot" | "incremental";
export type DroppedRows = "keep" | "withdraw";
export type WatermarkColumn = string | null;
export type Owner = string | null;
export type SetAt = string | null;
export type Paused = boolean;
export type PausedReason = string | null;
export type Read = (SqlRead | ApiRead | JsonRead) | null;
export type Kind = "sql";
export type Table = string;
export type Columns = string[];
export type Kind1 = "api";
export type Path = string;
export type RecordsAt = string | null;
export type Kind2 = "json";
export type Pattern1 = string;
export type RecordsAt1 = string | null;
export type Version = number;
export type CreatedBy = string;
export type CreatedAt = string;
export type UpdatedBy = string | null;
export type UpdatedAt = string | null;
export type NeedsAttention = string[];

export interface GovernanceEdited {
  source: SourceTable;
  needs_attention?: NeedsAttention;
  [k: string]: unknown;
}
export interface SourceTable {
  id: Id;
  dataset_id: DatasetId;
  connection_id: ConnectionId;
  name: Name;
  location: Location;
  connector_profile: ConnectorProfile;
  handling?: Handling;
  legal_basis?: LegalBasis;
  refresh?: SourceRefresh;
  read?: Read;
  version?: Version;
  created_by: CreatedBy;
  created_at: CreatedAt;
  updated_by?: UpdatedBy;
  updated_at?: UpdatedAt;
  [k: string]: unknown;
}
export interface Handling {
  [k: string]: unknown;
}
/**
 * When the source is read again (ADR-140 decision 15). A file source's watch takes each new
 * file whose whole name matches `pattern` (`*`, `?` and `[…]`, nothing else; ADR-110 Amendment
 * 4).
 */
export interface SourceRefresh {
  trigger?: Trigger;
  pattern?: Pattern;
  mode?: Mode;
  dropped_rows?: DroppedRows;
  watermark_column?: WatermarkColumn;
  owner?: Owner;
  set_at?: SetAt;
  paused?: Paused;
  paused_reason?: PausedReason;
  [k: string]: unknown;
}
/**
 * A table (or view) of a SQL connection; the columns named, or all of them.
 */
export interface SqlRead {
  kind?: Kind;
  table: Table;
  columns?: Columns;
}
/**
 * A path under the connection's base URL, and where each page's records are.
 */
export interface ApiRead {
  kind?: Kind1;
  path: Path;
  records_at?: RecordsAt;
}
/**
 * JSON files of the dataset's folder whose names match `pattern`, records at `records_at`.
 */
export interface JsonRead {
  kind?: Kind2;
  pattern: Pattern1;
  records_at?: RecordsAt1;
}
