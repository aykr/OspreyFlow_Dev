// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type EntityType = string;
export type Property = string;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Values =
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ];
/**
 * @minItems 1
 * @maxItems 30
 */
export type LinkTypes = [string, ...string[]];
export type Change = "add" | "multiply" | "floor" | "exclude";
export type Size = number;
export type Enabled = boolean;
export type Note = string | null;
export type Layer = "file" | "installation" | "case";
export type Version = number | null;

/**
 * One influencer in force for a case, and where it came from (`layer`); `version` is the
 * installation set's or the case override's version, None for the file's.
 */
export interface ActiveInfluencer {
  influencer: StrengthInfluencer;
  layer: Layer;
  version?: Version;
  [k: string]: unknown;
}
/**
 * One influencer (decision 1). `trigger` None is a direct-links influencer. `enabled` False,
 * in a higher layer, switches off the influencer of the same `id` below it.
 */
export interface StrengthInfluencer {
  id: Id;
  label: Label;
  trigger?: InfluencerTrigger | null;
  link_types: LinkTypes;
  change?: Change;
  size?: Size;
  enabled?: Enabled;
  note?: Note;
  [k: string]: unknown;
}
/**
 * What triggers an influencer: a record of `entity_type` whose `property` holds one of
 * `values`, which the viewer may see, at one end of the link or linked to both of its ends (the
 * record "evidences" the link).
 */
export interface InfluencerTrigger {
  entity_type: EntityType;
  property: Property;
  values: Values;
  [k: string]: unknown;
}
