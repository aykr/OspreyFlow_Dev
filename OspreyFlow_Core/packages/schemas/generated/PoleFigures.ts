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
export type Classes = PoleClassCount[];
export type Other = PoleTypeCount[];
export type Links = number;
export type CountedAt = string;

/**
 * The POLE summary of a case (ADR-126 decision 4), from the kept per-access-class counts the
 * Explore page reads: the reader's own, for the case's datasets, never a second count.
 *
 * `classes` is always the five classes in the order person, object, location, event,
 * organisation. `other` holds stored types the current ontology does not know, so no node
 * vanishes from the figures. `links` counts links of every type that is not `system`, a type the
 * ontology does not know included. `Alert` is in no figure: alerts are the Figures tab's own
 * subject. `counted_at` is when the kept counts were computed.
 */
export interface PoleFigures {
  classes: Classes;
  other?: Other;
  links: Links;
  counted_at: CountedAt;
  [k: string]: unknown;
}
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
