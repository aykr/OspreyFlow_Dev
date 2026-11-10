// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Text = string;

/**
 * The pipeline as YAML (*Show YAML*, ADR-140 decision 3): its nodes, each with its own
 * settings, and its lines, written by the Conduit. Editable in expert mode, and saved through
 * the same gates as the canvas's save (`PUT …/pipeline`): the text is read as a pipeline, never
 * run (`yaml.safe_load`).
 */
export interface PipelineYaml {
  text: Text;
}
