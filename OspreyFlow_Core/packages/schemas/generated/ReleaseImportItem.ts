// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Role = "domain_model" | "pipeline" | "reference_list" | "list_rows";
export type Name = string;
export type Action = "new_draft" | "replaces_draft";

export interface ReleaseImportItem {
  role: Role;
  name: Name;
  action: Action;
}
