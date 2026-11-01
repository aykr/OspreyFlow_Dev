// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ListName = string;
export type Source =
  "ofac_sdn" | "ofsi_consolidated" | "un_consolidated" | "eu_consolidated" | "opensanctions" | "uk_sanctions_list";
export type Location = string;
export type Dataset = string | null;
export type Use = "local_development" | "scale_testing" | "owner_run_demonstration";

/**
 * An administrator's subscription. `location` is a file inside the ingest folder; an OFAC
 * subscription also reads `ALT.CSV` and `ADD.CSV` beside it when they are there.
 */
export interface ScreeningSubscriptionInput {
  list_name: ListName;
  source: Source;
  location: Location;
  dataset?: Dataset;
  use?: Use;
  [k: string]: unknown;
}
