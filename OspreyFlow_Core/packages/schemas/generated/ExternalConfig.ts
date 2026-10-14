// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The managed server's address
 */
export type Host = string;
/**
 * Its port
 */
export type Port = number;
/**
 * The deployment's database on it
 */
export type Database = string;
/**
 * The login, which needs CREATEROLE and CREATEDB there
 */
export type User = string;
/**
 * Default: require. A managed server is reached over TLS.
 */
export type Sslmode = "require" | "verify-ca" | "verify-full";
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
 * The Blob storage account
 */
export type BlobAccount = string;
/**
 * The container media is kept in
 */
export type BlobContainer = string;
/**
 * The managed cache's address
 */
export type Host1 = string;
/**
 * Its port
 */
export type Port1 = number;
/**
 * Whether it is reached over TLS
 */
export type Tls = boolean;
/**
 * The domain's HTTPS address
 */
export type Url = string;

/**
 * What a cloud runs for the deployment instead of a container (ADR-114 decision 8).
 */
export interface ExternalConfig {
  postgres?: ExternalPostgres | null;
  object_store?: ExternalObjectStore | null;
  media?: ExternalMedia | null;
  valkey?: ExternalValkey | null;
  search?: ExternalSearch | null;
}
/**
 * A cloud's managed PostgreSQL (`05_DEPLOYMENT.md` §3a). The password is never here: it arrives
 * at apply as `OSPREY_POSTGRES_PASSWORD`, from the cloud's secret store.
 */
export interface ExternalPostgres {
  host: Host;
  port?: Port;
  database?: Database;
  user?: User;
  sslmode?: Sslmode;
}
/**
 * A cloud's S3 (`05_DEPLOYMENT.md` §3a) for staging, site images, tiles, backups and media.
 */
export interface ExternalObjectStore {
  endpoint: Endpoint;
  region: Region;
  credentials?: Credentials;
  bucket_prefix?: BucketPrefix;
}
/**
 * Media on Azure Blob (`05_DEPLOYMENT.md` §3a); the account key arrives at apply as
 * `AZURE_STORAGE_KEY`.
 */
export interface ExternalMedia {
  blob_account: BlobAccount;
  blob_container?: BlobContainer;
}
/**
 * A cloud's managed Valkey or Redis (`05_DEPLOYMENT.md` §3b: ElastiCache, Azure Cache for
 * Redis); a cluster's replicas share it. Its password, if any, arrives as `VALKEY_PASSWORD`.
 */
export interface ExternalValkey {
  host: Host1;
  port?: Port1;
  tls?: Tls;
}
/**
 * A cloud's managed OpenSearch (`05_DEPLOYMENT.md` §3b: Amazon OpenSearch Service).
 */
export interface ExternalSearch {
  url: Url;
}
