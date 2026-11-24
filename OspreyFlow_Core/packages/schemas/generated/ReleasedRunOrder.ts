// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ExportedVersion = number;
/**
 * @minItems 1
 */
export type RunsAfter = [ReleasedRunOrderLink, ...ReleasedRunOrderLink[]];
export type Pipeline = string;
/**
 * @minItems 1
 */
export type After = [string, ...string[]];

/**
 * The run order's file: the links among the bundle's own pipelines, never who saved it or
 * when. An import writes it as a new version of the receiving dataset's order, its pipelines
 * mapped to the drafts the import makes.
 */
export interface ReleasedRunOrder {
  exported_version: ExportedVersion;
  runs_after: RunsAfter;
}
/**
 * One pipeline and the pipelines it runs after, each by its `pipeline_id` in this bundle.
 */
export interface ReleasedRunOrderLink {
  pipeline: Pipeline;
  after: After;
}
