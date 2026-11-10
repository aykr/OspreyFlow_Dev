// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DryRun = boolean;
export type Name = string;
export type Version = string;
export type Role = "domain_model" | "pipeline" | "reference_list" | "list_rows";
export type Name1 = string;
export type Action = "new_draft" | "replaces_draft";
export type Items = ReleaseImportItem[];
export type Refused = string[];
export type MissingConnections = string[];
export type Notes = string[];

/**
 * What an import writes, or with `--dry-run` would write: always drafts. `refused` names in
 * words why a bundle cannot be imported; nothing is written when it is not empty.
 */
export interface ReleaseImportPlan {
  dry_run: DryRun;
  release?: ReleaseMetadata | null;
  items?: Items;
  refused?: Refused;
  missing_connections?: MissingConnections;
  notes?: Notes;
}
export interface ReleaseMetadata {
  name: Name;
  version: Version;
}
export interface ReleaseImportItem {
  role: Role;
  name: Name1;
  action: Action;
}
