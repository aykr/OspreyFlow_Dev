// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The five-class upper ontology. Closed: a deployment may add entity
 * types, never a sixth POLE class — `01_DOMAIN_MODEL.md` §1.1.
 */
export type PoleClass = "person" | "object" | "location" | "event" | "organisation";
export type Total = number;
export type EntityType = string;
export type Count = number;
export type Types = PoleTypeCount[];

/**
 * One POLE class: its total, and its types largest first, then by name, with no zero rows.
 */
export interface PoleClassCount {
  pole_class: PoleClass;
  total: Total;
  types?: Types;
  [k: string]: unknown;
}
/**
 * How many nodes of one entity type the reader can see (ADR-126 decision 4). `entity_type` is
 * a closed ontology type name, never an entity's own text.
 */
export interface PoleTypeCount {
  entity_type: EntityType;
  count: Count;
  [k: string]: unknown;
}
