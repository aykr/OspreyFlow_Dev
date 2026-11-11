// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "athena";
export type Region = string;
export type Workgroup = string;
export type Catalog = string;
/**
 * @minItems 1
 */
export type Databases = [string, ...string[]];
export type ResultsLocation = string | null;

/**
 * Amazon Athena, read-only (L1.9): a workgroup, the catalog and the databases its sources may
 * read. **No key and no secret**, as for S3. Athena writes each query's results to S3 itself: to
 * the workgroup's own location, or to `results_location` when the workgroup names none.
 */
export interface AthenaConnectionSettings {
  kind?: Kind;
  region: Region;
  workgroup?: Workgroup;
  catalog?: Catalog;
  databases: Databases;
  results_location?: ResultsLocation;
}
