// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type InvestigationId = string;
export type Title = string;
export type CreatedBy = string;
export type CreatedAt = string;
export type UpdatedAt = string;
export type Version = number;
export type PublishedAt = string;
export type PublishedBy = string;
export type PublishedByName = string | null;
export type WithdrawnAt = string | null;
export type WithdrawnBy = string | null;
export type WithdrawnByName = string | null;
export type WithdrawalReason = string | null;
export type Versions = PackVersionSummary[];

export interface ReportPack {
  id: Id;
  investigation_id: InvestigationId;
  title: Title;
  created_by: CreatedBy;
  created_at: CreatedAt;
  updated_at: UpdatedAt;
  versions?: Versions;
  [k: string]: unknown;
}
export interface PackVersionSummary {
  version: Version;
  published_at: PublishedAt;
  published_by: PublishedBy;
  published_by_name?: PublishedByName;
  withdrawn_at?: WithdrawnAt;
  withdrawn_by?: WithdrawnBy;
  withdrawn_by_name?: WithdrawnByName;
  withdrawal_reason?: WithdrawalReason;
  [k: string]: unknown;
}
