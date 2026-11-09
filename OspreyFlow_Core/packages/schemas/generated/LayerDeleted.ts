// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationId = string;
export type Words = string;

/**
 * A removed case's layer deleted, in words. No count of what was withdrawn: it would include
 * what the deleter may not see (rule 7). Promoted items are untouched.
 */
export interface LayerDeleted {
  investigation_id: InvestigationId;
  words: Words;
}
