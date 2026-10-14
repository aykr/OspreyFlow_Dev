// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The machine's name
 */
export type Name = string;
/**
 * Where the machine is reached
 */
export type Address = string;
/**
 * What runs on it
 */
export type Roles = string[];
export type Hosts = ClusterHost[];
/**
 * The Kubernetes namespace the deployment is installed in (05_DEPLOYMENT.md §3b)
 */
export type Namespace = string;
/**
 * The storage class each store's own volumes use; the cluster's default when unset
 */
export type StorageClass = string | null;
/**
 * Required for a cluster: the storage class of the one volume every Conduit shares (ReadWriteMany) — EFS on AWS, Azure Files on Azure
 */
export type SharedStorageClass = string | null;

/**
 * Only meaningful at `profile: cluster`; declarable (and empty) at the other two so a profile
 * change does not need the file restructured.
 */
export interface ClusterConfig {
  hosts?: Hosts;
  namespace?: Namespace;
  storage_class?: StorageClass;
  shared_storage_class?: SharedStorageClass;
}
/**
 * One declared machine. `05_DEPLOYMENT.md` §2.1's Preflight screen runs "for `cluster`
 * connectivity to every declared host" against this list — Stage 2 §2's check, this schema's
 * declaration.
 */
export interface ClusterHost {
  name: Name;
  address: Address;
  roles?: Roles;
}
