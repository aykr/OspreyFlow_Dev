// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "amount";
export type LinkType = string;
export type AmountProperty = string;
export type Over = number;
export type WithinDays = number;

/**
 * A total of a declared amount on a link type's events over X within D days.
 */
export interface AmountFrequency {
  kind?: Kind;
  link_type: LinkType;
  amount_property: AmountProperty;
  over: Over;
  within_days: WithinDays;
  [k: string]: unknown;
}
