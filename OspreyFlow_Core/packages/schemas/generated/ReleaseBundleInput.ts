// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * A bundle sent to the import route: each file's text by its path (`release.yaml` the
 * manifest). Bounded so an upload cannot be unbounded.
 */
export interface ReleaseBundleInput {
  files: Files;
}
export interface Files {
  [k: string]: string;
}
