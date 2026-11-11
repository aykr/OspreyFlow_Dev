// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "s3";
export type Region = string;
export type Bucket = string;
export type Prefix = string;

/**
 * An S3 bucket, read-only (L1.9; ADR-148 decisions 4 and 7). **No key and no secret**: the read
 * signs in as the deployment's own cloud identity (on the `cloud-platform` profile, the
 * namespace's IAM role), so nothing here could hold a credential. The host is made from the
 * region and the bucket, never typed, and must be on the deployment's egress allow-list.
 */
export interface S3ConnectionSettings {
  kind?: Kind;
  region: Region;
  bucket: Bucket;
  prefix?: Prefix;
}
