// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type Trigger = InfluencerTrigger | DatasetTrigger | null;
export type Kind = "record";
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
export type Kind1 = "dataset";
/**
 * @minItems 1
 * @maxItems 20
 */
export type Datasets =
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
export type Influencers = ActiveInfluencer[];
export type DirectLinkTypes = string[];
export type SwitchedOff = string[];
export type RarityNote = string;
export type Composition = "standard" | "client_parity";
export type CompositionLayer = "file" | "installation" | "case";
export type RarityMeasure = "share" | "idf";
export type CaseVersion = number | null;
export type CaseSetByName = string | null;
/**
 * @maxItems 50
 */
export type Added = StrengthInfluencer[];
/**
 * @maxItems 50
 */
export type SwitchedOff1 = string[];
export type Composition1 = ("standard" | "client_parity") | null;
export type Words = string;
export type CanOverride = boolean;

/**
 * `GET /v1/investigations/{id}/strength-influencers`: the legend for the case, and its own
 * override as its Author last set it (None: it has none).
 */
export interface CaseInfluencers {
  legend: StrengthLegend;
  override?: CaseInfluencersInput | null;
  can_override?: CanOverride;
  [k: string]: unknown;
}
/**
 * What the legend box says about connection strength (decision 7): the influencers in force,
 * each marked by its layer (a case override as such), which link types count as direct, which
 * shipped or installation influencers the case has switched off, and the rarity note.
 */
export interface StrengthLegend {
  influencers: Influencers;
  direct_link_types: DirectLinkTypes;
  switched_off?: SwitchedOff;
  rarity_note: RarityNote;
  composition?: Composition;
  composition_layer?: CompositionLayer;
  rarity_measure?: RarityMeasure;
  case_version?: CaseVersion;
  case_set_by_name?: CaseSetByName;
  [k: string]: unknown;
}
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
 * in a higher layer, switches off the influencer of the same `id` below it. `link_types` may
 * name `SHARED_VALUE`: a pair linked through a shared value (Amendment 2).
 */
export interface StrengthInfluencer {
  id: Id;
  label: Label;
  trigger?: Trigger;
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
  kind?: Kind;
  entity_type: EntityType;
  property: Property;
  values: Values;
  [k: string]: unknown;
}
/**
 * ADR-139 Amendment 2, ruling 3: an influencer triggered by a dataset (or the source loaded
 * into it), as the client's `abs_add` is by the table it is called on. It applies to every link
 * evidenced in one of `datasets`: a stored link that belongs to it, or a pair linked through a
 * shared value in it. It applies only where the viewer may read that dataset, so a link seen
 * through another dataset is never thickened by one they cannot read (rule 3).
 */
export interface DatasetTrigger {
  kind?: Kind1;
  datasets: Datasets;
  [k: string]: unknown;
}
/**
 * A case's override, set by its Author (decision 3): influencers added for this case, and the
 * ids of installation-wide (or shipped) influencers switched off in it.
 */
export interface CaseInfluencersInput {
  added?: Added;
  switched_off?: SwitchedOff1;
  composition?: Composition1;
  words?: Words;
  [k: string]: unknown;
}
