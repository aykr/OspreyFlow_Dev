// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type Kind = "reference" | "screening";
export type Version = number;
export type DeploymentWide = boolean;

/**
 * A list a dataset's rule or Lookup may read: its own, or a deployment-wide one it subscribes
 * to. Never another dataset's.
 */
export interface OfferedList {
  id: Id;
  name: Name;
  kind: Kind;
  version: Version;
  deployment_wide: DeploymentWide;
  [k: string]: unknown;
}
