// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type BlobAccount = string;
export type BlobContainer = string;

/**
 * Media on Azure Blob (`05_DEPLOYMENT.md` §3a); the account key arrives at apply as
 * `AZURE_STORAGE_KEY`.
 */
export interface ExternalMedia {
  blob_account: BlobAccount;
  blob_container?: BlobContainer;
}
