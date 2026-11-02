// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Version = number;
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
export type Influencers = StrengthInfluencer[];
export type Status = "pending" | "approved" | "sent_back";
export type ProposedBy = string;
export type ProposedAt = string;
export type Words = string;
export type DecidedBy = string | null;
export type DecidedAt = string | null;
export type DecisionWords = string | null;
export type InForce = boolean;
export type ProposedByName = string | null;
export type DecidedByName = string | null;
export type Versions = InfluencerSetVersion[];
export type Defaults = StrengthInfluencer[];

/**
 * `GET /v1/strength-influencers`: every version, newest first, and the developer defaults
 * that apply where no approved version names an influencer.
 */
export interface InfluencerSetHistory {
  versions: Versions;
  defaults: Defaults;
  [k: string]: unknown;
}
/**
 * One version of the installation-wide set, kept whole with who proposed and who decided it
 * (decision 3). Names are resolved when the read is served, never stored (ADR-106).
 */
export interface InfluencerSetVersion {
  version: Version;
  influencers: Influencers;
  status: Status;
  proposed_by: ProposedBy;
  proposed_at: ProposedAt;
  words?: Words;
  decided_by?: DecidedBy;
  decided_at?: DecidedAt;
  decision_words?: DecisionWords;
  in_force?: InForce;
  proposed_by_name?: ProposedByName;
  decided_by_name?: DecidedByName;
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
