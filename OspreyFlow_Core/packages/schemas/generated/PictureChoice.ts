// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DocumentId = string;
export type Marking = string;

/**
 * C17 (b): a picture the case already holds, linked to the drawn node by a `DEPICTS` in the
 * layer; the image stays in its dataset.
 */
export interface PictureChoice {
  document_id: DocumentId;
  marking: Marking;
}
