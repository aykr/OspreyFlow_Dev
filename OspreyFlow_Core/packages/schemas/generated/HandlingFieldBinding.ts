// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Field = string;

/**
 * One part of an element's marking read from a source column per row (ADR-127 decision 3):
 * `{field: <column>}`. An empty cell takes the element's default for that part; a cell may only
 * tighten it (`merge_handling`'s order), and a unit must be one the recipe declares.
 */
export interface HandlingFieldBinding {
  field: Field;
}
