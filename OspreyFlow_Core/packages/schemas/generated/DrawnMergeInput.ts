// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type TargetDatasetId = string;
/**
 * @minItems 1
 * @maxItems 5000
 */
export type ItemIds = [string, ...string[]];
export type Drawn = string;
export type Loaded = string;
/**
 * @maxItems 5000
 */
export type Matches = MatchPick[];
export type Kind = "node" | "link";
export type DrawnType = string;
export type TargetType = string | null;
export type DrawnProperty = string;
export type TargetProperty = string | null;
/**
 * @maxItems 200
 */
export type Properties = PropertyMapping[];
/**
 * @maxItems 500
 */
export type Mapping = TypeChoice[];

/**
 * The items ticked and the matches chosen; every check runs again at the route.
 */
export interface DrawnMergeInput {
  target_dataset_id: TargetDatasetId;
  item_ids: ItemIds;
  matches?: Matches;
  mapping?: Mapping;
}
export interface MatchPick {
  drawn: Drawn;
  loaded: Loaded;
}
/**
 * The merger's choice for one drawn type: the target's type (`None`: left out) and, when it
 * is another type, each drawn property's place in it. A drawn type not listed takes the sheet's
 * proposal.
 */
export interface TypeChoice {
  kind: Kind;
  drawn_type: DrawnType;
  target_type: TargetType;
  properties?: Properties;
}
/**
 * One drawn property and the property (or identifier) of the chosen type it goes in as, or
 * `None`: not carried (it stays on the drawing, read-only, and is said).
 */
export interface PropertyMapping {
  drawn_property: DrawnProperty;
  target_property: TargetProperty;
}
