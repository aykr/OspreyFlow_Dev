// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ExportedVersion = number;
export type Name = string;
export type Kind = "entity_type" | "link_type" | "property";
export type OnType = string | null;
export type AddedIn = number;
export type RetiredIn = number | null;
export type Extensions = ModelExtension[];
export type ReferenceLists = string[];

/**
 * The domain model's file: what a draft is made of, never who made it or when it went live.
 */
export interface ReleasedDomainModel {
  exported_version: ExportedVersion;
  packs?: Packs;
  extensions?: Extensions;
  reference_lists?: ReferenceLists;
}
export interface Packs {
  [k: string]: number;
}
/**
 * A type or property the dataset's own model adds beyond the core and its packs (ADR-140
 * decision 4; today's analyst-proposed type, ADR-090). Retired, never deleted: a rename is "add
 * the new, retire the old".
 */
export interface ModelExtension {
  name: Name;
  kind: Kind;
  on_type?: OnType;
  added_in: AddedIn;
  retired_in?: RetiredIn;
}
