// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
/**
 * The five-class upper ontology. Closed: a deployment may add entity
 * types, never a sixth POLE class — `01_DOMAIN_MODEL.md` §1.1.
 */
export type PoleClass = "person" | "object" | "location" | "event" | "organisation";
export type Channel = string;
export type Shape = string;
export type Icon = string | null;
export type Property = string;
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

export interface EntityTypeDef {
  name: Name;
  pole_class: PoleClass;
  channel: Channel;
  shape: Shape;
  icon?: Icon;
  icon_by_value?: IconByValue | null;
  identifiers?: Identifiers;
  properties?: Properties;
  resolution?: ResolutionConfig | null;
  [k: string]: unknown;
}
/**
 * ADR-128 Decision 4: an entity type's icon chosen by the value of one of its enum properties.
 * `icons` maps some of the property's values to glyph names; the loader checks that the property
 * is an enum of the type and that each key is one of its values and each name is on the closed
 * icon list.
 */
export interface IconByValue {
  property: Property;
  icons: Icons;
  [k: string]: unknown;
}
export interface Icons {
  [k: string]: string;
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
