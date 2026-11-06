// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LegalBasis = string | null;
export type Trigger = "manual" | "watch";
export type Pattern = string | null;
export type Mode = "snapshot" | "incremental";
export type DroppedRows = "keep" | "withdraw";
export type WatermarkColumn = string | null;
export type Owner = string | null;
export type Paused = boolean;
export type PausedReason = string | null;

/**
 * An edit of a source's governance, audited; a new version of the source.
 */
export interface SourceGovernanceInput {
  handling: Handling;
  legal_basis?: LegalBasis;
  refresh?: SourceRefresh | null;
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
  paused?: Paused;
  paused_reason?: PausedReason;
  [k: string]: unknown;
}
