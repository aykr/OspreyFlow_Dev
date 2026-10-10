// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Source = string;
export type Target = string;

/**
 * A data dependency: `source` feeds `target`. The graph is acyclic (validated at save).
 */
export interface PipelineEdge {
  source: Source;
  target: Target;
  [k: string]: unknown;
}
