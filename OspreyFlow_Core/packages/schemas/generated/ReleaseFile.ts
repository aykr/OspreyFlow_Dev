// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Path = string;
export type Role = "domain_model" | "pipeline" | "reference_list" | "list_rows";
export type Sha256 = string;

export interface ReleaseFile {
  path: Path;
  role: Role;
  sha256: Sha256;
}
