// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Each drawn node's picture on a board that the reader may see: node id to Document id.
 */
export interface BoardPictures {
  pictures?: Pictures;
  [k: string]: unknown;
}
export interface Pictures {
  [k: string]: string;
}
