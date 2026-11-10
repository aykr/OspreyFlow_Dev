// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Apiversion = "ospreyflow.io/v1";
export type Kind = "DatasetRelease";
export type Name = string;
export type Version = string;
export type DomainModel = string;
export type Pipelines = string[];
export type ReferenceLists = string[];
export type Connections = string[];
export type Path = string;
export type Role = "domain_model" | "pipeline" | "reference_list" | "list_rows";
export type Sha256 = string;
export type Files = ReleaseFile[];

/**
 * The manifest (`release.yaml`). Its JSON schema is `packages/schemas/release.schema.json`.
 */
export interface DatasetRelease {
  apiVersion: Apiversion;
  kind: Kind;
  metadata: ReleaseMetadata;
  spec: ReleaseSpec;
}
export interface ReleaseMetadata {
  name: Name;
  version: Version;
}
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
