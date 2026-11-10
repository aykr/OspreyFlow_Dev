// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Bpmn = string;
export type Dmn = string;

/**
 * The two files of one rule, as their text: what the editor's *Import* sends.
 */
export interface RuleFilesUpload {
  bpmn: Bpmn;
  dmn: Dmn;
  [k: string]: unknown;
}
