// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Version = number;
export type Name = string;
/**
 * The five-class upper ontology. Closed: a deployment may add entity
 * types, never a sixth POLE class — `01_DOMAIN_MODEL.md` §1.1.
 */
export type PoleClass = "person" | "object" | "location" | "event" | "organisation";
export type Channel = string;
export type Shape = string;
export type Identifiers = string[];
export type Name1 = string;
export type PropertyType = "string" | "string[]" | "date" | "datetime" | "integer" | "float" | "boolean" | "enum";
export type Indexed = boolean;
export type Required = boolean;
export type Sensitivity = ("low" | "medium" | "high") | null;
export type Values = string[] | null;
export type Properties = PropertyDef[];
export type Blocking = string[];
export type Comparisons = string[];
export type EntityTypes = EntityTypeDef[];
export type Name2 = string;
export type From = string[];
export type To = string[];
export type Directed = boolean;
export type Temporal = boolean;
export type System = boolean;
export type Properties1 = PropertyDef[];
export type EdgeTypes = EdgeTypeDef[];

/**
 * The loaded, validated ontology — what `GraphPort.apply_schema` takes
 * and what the schema/migration runner turns into vertex/edge types and
 * the indexes in `04_VAULT_BACKEND.md` §1.4.
 */
export interface OntologySchema {
  version: Version;
  entity_types: EntityTypes;
  edge_types: EdgeTypes;
  [k: string]: unknown;
}
export interface EntityTypeDef {
  name: Name;
  pole_class: PoleClass;
  channel: Channel;
  shape: Shape;
  identifiers?: Identifiers;
  properties?: Properties;
  resolution?: ResolutionConfig | null;
  [k: string]: unknown;
}
export interface PropertyDef {
  name: Name1;
  type: PropertyType;
  indexed?: Indexed;
  required?: Required;
  sensitivity?: Sensitivity;
  values?: Values;
  [k: string]: unknown;
}
/**
 * Splink blocking/comparison rules per entity type — `01_DOMAIN_MODEL.md`
 * §4. Consumed by `services/resolve` from Phase 6 on; carried here because
 * it is part of the ontology's per-type shape.
 */
export interface ResolutionConfig {
  blocking?: Blocking;
  comparisons?: Comparisons;
  [k: string]: unknown;
}
export interface EdgeTypeDef {
  name: Name2;
  from: From;
  to: To;
  directed?: Directed;
  temporal?: Temporal;
  system?: System;
  properties?: Properties1;
  [k: string]: unknown;
}
