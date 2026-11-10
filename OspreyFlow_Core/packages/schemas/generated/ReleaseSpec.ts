// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DomainModel = string;
export type Pipelines = string[];
export type ReferenceLists = string[];
export type Connections = string[];
export type Path = string;
export type Role = "domain_model" | "pipeline" | "reference_list" | "list_rows";
export type Sha256 = string;
export type Files = ReleaseFile[];

export interface ReleaseSpec {
  domain_model: DomainModel;
  packs?: Packs;
  pipelines?: Pipelines;
  reference_lists?: ReferenceLists;
  connections?: Connections;
  files?: Files;
}
export interface Packs {
  [k: string]: number;
}
export interface ReleaseFile {
  path: Path;
  role: Role;
  sha256: Sha256;
}
