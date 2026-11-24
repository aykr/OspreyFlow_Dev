// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Pipeline = string;
/**
 * @minItems 1
 */
export type After = [string, ...string[]];

/**
 * One pipeline and the pipelines it runs after, each by its `pipeline_id` in this bundle.
 */
export interface ReleasedRunOrderLink {
  pipeline: Pipeline;
  after: After;
}
