// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PackId = string;
export type Title = string;
export type Version = number;
export type PublishedAt = string;
export type PublishedBy = string;
export type PublishedByName = string | null;

export interface PublishedPackSummary {
  pack_id: PackId;
  title: Title;
  version: Version;
  published_at: PublishedAt;
  published_by: PublishedBy;
  published_by_name?: PublishedByName;
  [k: string]: unknown;
}
