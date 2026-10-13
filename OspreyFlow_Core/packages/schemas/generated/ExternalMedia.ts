// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The Blob storage account
 */
export type BlobAccount = string;
/**
 * The container media is kept in
 */
export type BlobContainer = string;

/**
 * Media on Azure Blob (`05_DEPLOYMENT.md` §3a); the account key arrives at apply as
 * `AZURE_STORAGE_KEY`.
 */
export interface ExternalMedia {
  blob_account: BlobAccount;
  blob_container?: BlobContainer;
}
