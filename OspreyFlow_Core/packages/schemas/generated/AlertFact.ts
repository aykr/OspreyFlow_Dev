// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type AlertId = string;
export type InvestigationScope = string | null;
export type Kind = "typology" | "hotlist" | "monitor" | "analyst" | "drawn_watch";
export type Rule = string;
export type Typology = string | null;
export type Severity = "high" | "medium" | "low";
export type Outcome =
  "open" | "claimed" | "true_positive" | "false_positive" | "duplicate" | "no_further_action" | "referred" | "closed";
export type RaisedAt = string;
export type OwnerId = string;
export type Audience = "case" | "team" | "owner" | "routed";
export type Team = string | null;
export type DatasetId = string | null;
export type Handlings = Handling[] | null;
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;

/**
 * One alert as the analytics store keeps it for alert trends (ADR-134 decision 3): written by
 * the Conduit whenever the alert is raised or changes, replacing what was kept for it before.
 *
 * `handlings` is every handling the alert rests on — each node, link and transaction it cites —
 * as they were when it was raised. A reader counts the alert only if they may view all of them
 * (rule 3, all or nothing, in the query). `None` means they are not known (an alert raised before
 * this was kept): such an alert is counted for no one, never guessed. An empty list is an alert
 * that cites nothing (a `notify` stub), counted for its audience alone.
 */
export interface AlertFact {
  alert_id: AlertId;
  investigation_scope?: InvestigationScope;
  kind: Kind;
  rule: Rule;
  typology?: Typology;
  severity: Severity;
  outcome: Outcome;
  raised_at: RaisedAt;
  owner_id: OwnerId;
  audience: Audience;
  team?: Team;
  dataset_id?: DatasetId;
  handlings?: Handlings;
  [k: string]: unknown;
}
export interface Handling {
  classification: Classification;
  handling_code: HandlingCode;
  action_code?: ActionCode;
  sanitisation_code?: SanitisationCode;
  originator: OrgUnitId;
  owning_unit: OrgUnitId;
  review_date?: ReviewDate;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
