// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type RowIndex = number;
export type HandlingOverride = {
  [k: string]: unknown;
} | null;
export type ProvenanceOverride = {
  [k: string]: unknown;
} | null;

/**
 * Body of `POST /v1/ingest/recipes/{id}/map/handling-preview` — what
 * `preview_handling_and_provenance()` (`services/ingest/engine.py`) would
 * compute for one in-progress element, before it is saved onto the
 * template at all.
 */
export interface MapHandlingPreviewRequest {
  row_index: RowIndex;
  handling_override?: HandlingOverride;
  provenance_override?: ProvenanceOverride;
  [k: string]: unknown;
}
