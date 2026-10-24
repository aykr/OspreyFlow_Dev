// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EntityType = string;
export type Count = number;

/**
 * How many nodes of one entity type the reader can see (ADR-126 decision 4). `entity_type` is
 * a closed ontology type name, never an entity's own text.
 */
export interface PoleTypeCount {
  entity_type: EntityType;
  count: Count;
  [k: string]: unknown;
}
