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
export type EntityTypes = EntityTypeDef[];
export type Name2 = string;
export type From = string[];
export type To = string[];
export type Directed = boolean;
export type Temporal = boolean;
export type System = boolean;
export type Basis = ("direct" | "probabilistic") | null;
export type Colour = string | null;
export type Thickness = number | null;
export type Label = string | null;
export type Aliases = string[];
export type DirectSince = string | null;
export type AnalystDefined = boolean;
export type Hidden = boolean;
export type Properties1 = PropertyDef[];
export type EdgeTypes = EdgeTypeDef[];
export type OverlayRevision = number;

/**
 * The loaded, validated ontology — what `GraphPort.apply_schema` takes
 * and what the schema/migration runner turns into vertex/edge types and
 * the indexes in `04_VAULT_BACKEND.md` §1.4.
 */
export interface OntologySchema {
  version: Version;
  entity_types: EntityTypes;
  edge_types: EdgeTypes;
  storage_aliases?: StorageAliases;
  overlay_revision?: OverlayRevision;
  packs?: Packs;
  type_packs?: TypePacks;
  [k: string]: unknown;
}
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
export interface EdgeTypeDef {
  name: Name2;
  from: From;
  to: To;
  directed?: Directed;
  temporal?: Temporal;
  system?: System;
  basis?: Basis;
  colour?: Colour;
  thickness?: Thickness;
  label?: Label;
  aliases?: Aliases;
  direct_since?: DirectSince;
  analyst_defined?: AnalystDefined;
  hidden?: Hidden;
  properties?: Properties1;
  [k: string]: unknown;
}
export interface StorageAliases {
  [k: string]: string;
}
export interface Packs {
  [k: string]: number;
}
export interface TypePacks {
  [k: string]: string;
}
