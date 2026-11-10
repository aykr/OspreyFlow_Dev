// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type Kind = "source" | "composite";
export type SecondPerson = boolean;
export type Version = number;
export type Name1 = string;
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
export type Name2 = string;
export type PropertyType = "string" | "string[]" | "date" | "datetime" | "integer" | "float" | "boolean" | "enum";
export type Indexed = boolean;
export type Required = boolean;
export type Sensitivity = ("low" | "medium" | "high") | null;
export type Values = string[] | null;
export type Properties = PropertyDef[];
export type Blocking = string[];
export type Comparisons = string[];
export type EntityTypes = EntityTypeDef[];
export type Name3 = string;
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
export type Id1 = string;
export type Name4 = string;
export type Kind1 = "reference" | "screening";
export type Version1 = number;
export type DeploymentWide = boolean;
export type Lists = OfferedList[];

/**
 * A dataset a rule may be declared on: the case's chosen source or composite, never a layer or
 * a drawn dataset (ADR-146 decision 3). `ontology` is the deployment's ontology narrowed to the
 * dataset's live model (its whole ontology while it has no model yet, as boards read it), so the
 * conditions offer no type outside it; `lists` are the screening and reference lists it may read
 * (its own and those it subscribes to); `second_person` says *Make live* waits for another
 * person's approval (the dataset's policy, ADR-145 A3).
 */
export interface RuleDatasetOffer {
  id: Id;
  name: Name;
  kind: Kind;
  second_person: SecondPerson;
  ontology: OntologySchema;
  lists?: Lists;
  [k: string]: unknown;
}
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
  name: Name1;
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
  name: Name2;
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
  name: Name3;
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
/**
 * A list a dataset's rule or Lookup may read: its own, or a deployment-wide one it subscribes
 * to. Never another dataset's.
 */
export interface OfferedList {
  id: Id1;
  name: Name4;
  kind: Kind1;
  version: Version1;
  deployment_wide: DeploymentWide;
  [k: string]: unknown;
}
