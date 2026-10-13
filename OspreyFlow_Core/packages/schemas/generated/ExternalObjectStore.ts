// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Host and port, no scheme: always HTTPS
 */
export type Endpoint = string;
/**
 * The region the buckets live in
 */
export type Region = string;
/**
 * Default: instance — the server's own cloud identity, no key anywhere; `keys` reads OSPREY_S3_ACCESS_KEY and OSPREY_S3_SECRET_KEY at apply.
 */
export type Credentials = "instance" | "keys";
/**
 * Each bucket is <prefix><name>, as OpenTofu made them
 */
export type BucketPrefix = string;

/**
 * A cloud's S3 (`05_DEPLOYMENT.md` §3a) for staging, site images, tiles, backups and media.
 */
export interface ExternalObjectStore {
  endpoint: Endpoint;
  region: Region;
  credentials?: Credentials;
  bucket_prefix?: BucketPrefix;
}
