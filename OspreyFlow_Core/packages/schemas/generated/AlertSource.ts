// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type RuleId = string;
export type Name = string;
export type Source = "rule" | "watch";
export type Kind = "rule" | "hotlist" | "watched_pattern";
export type Maker = string;
export type MakerName = string | null;
export type DatasetId = string | null;
export type Owner = string;
export type State = "draft" | "live" | "stopped";
export type ExpiresOn = string | null;
export type LastFiredAt = string | null;
export type Alerts30Days = number;
export type NotOfInterest = number | null;
export type AlertId = string;
export type Until = string;
export type Reason = string;
export type By = string;
export type Suppressed = SuppressedAlert[];

/**
 * One row of *What raises alerts* (ADR-146 decision 5): a rule or a watch, whoever made it.
 * Its counts are the reader's queue's, so an alert they may not see is not counted (rule 7).
 */
export interface AlertSource {
  id: Id;
  rule_id: RuleId;
  name: Name;
  source: Source;
  kind: Kind;
  maker: Maker;
  maker_name?: MakerName;
  dataset_id?: DatasetId;
  owner: Owner;
  state: State;
  expires_on?: ExpiresOn;
  last_fired_at?: LastFiredAt;
  alerts_30_days?: Alerts30Days;
  not_of_interest?: NotOfInterest;
  suppressed?: Suppressed;
  [k: string]: unknown;
}
export interface SuppressedAlert {
  alert_id: AlertId;
  until: Until;
  reason: Reason;
  by: By;
  [k: string]: unknown;
}
