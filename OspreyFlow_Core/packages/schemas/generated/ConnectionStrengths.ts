// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeId = string;
export type EdgeType = string;
export type BaseWeight = number;
export type Strength = number;
export type ParameterSet = string | null;
export type Heavy = number | null;
export type Fixed = number | null;
export type Occurrences = number;
export type LastSeen = string | null;
export type Id = string;
export type Label = string;
export type Change = "add" | "multiply" | "floor" | "exclude";
export type Size = number;
export type Layer = "file" | "installation" | "case";
export type RecordKind = string | null;
export type Dataset = string | null;
export type Applied = AppliedInfluencer[];
export type Composition = "standard" | "client_parity";
export type RarityTerm = number | null;
export type RawSum = number | null;
export type Dataset1 = string | null;
export type Links = LinkStrength[];
export type Id1 = string;
export type Label1 = string;
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
export type Change1 = "add" | "multiply" | "floor" | "exclude";
export type Size1 = number;
export type Enabled = boolean;
export type Note = string | null;
export type Layer1 = "file" | "installation" | "case";
export type Version = number | null;
export type Influencers = ActiveInfluencer[];
export type DirectLinkTypes = string[];
export type SwitchedOff = string[];
export type RarityNote = string;
export type Composition1 = "standard" | "client_parity";
export type CompositionLayer = "file" | "installation" | "case";
export type RarityMeasure = "share" | "idf";
export type CaseVersion = number | null;
export type CaseSetByName = string | null;

export interface ConnectionStrengths {
  links: Links;
  legend: StrengthLegend;
  [k: string]: unknown;
}
/**
 * A link's connection strength as its viewer may see it (decision 5), with what explains it
 * (decision 9): the stored weight, the rule and version it was computed under, what is heavy for
 * its type, and each influencer that changed it. Never a corpus-wide count (ADR-122).
 */
export interface LinkStrength {
  edge_id: EdgeId;
  edge_type: EdgeType;
  base_weight: BaseWeight;
  strength: Strength;
  parameter_set?: ParameterSet;
  heavy?: Heavy;
  fixed?: Fixed;
  occurrences?: Occurrences;
  last_seen?: LastSeen;
  applied?: Applied;
  composition?: Composition;
  rarity_term?: RarityTerm;
  raw_sum?: RawSum;
  dataset?: Dataset1;
  [k: string]: unknown;
}
/**
 * One influencer that changed one link, and the kind of record that evidenced it (None for a
 * direct-links influencer). Only a record the viewer may see is ever named.
 */
export interface AppliedInfluencer {
  id: Id;
  label: Label;
  change: Change;
  size: Size;
  layer: Layer;
  record_kind?: RecordKind;
  dataset?: Dataset;
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
  composition?: Composition1;
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
  layer: Layer1;
  version?: Version;
  [k: string]: unknown;
}
/**
 * One influencer (decision 1). `trigger` None is a direct-links influencer. `enabled` False,
 * in a higher layer, switches off the influencer of the same `id` below it. `link_types` may
 * name `SHARED_VALUE`: a pair linked through a shared value (Amendment 2).
 */
export interface StrengthInfluencer {
  id: Id1;
  label: Label1;
  trigger?: Trigger;
  link_types: LinkTypes;
  change?: Change1;
  size?: Size1;
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
