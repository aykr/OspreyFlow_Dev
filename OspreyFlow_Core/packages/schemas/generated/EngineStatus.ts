// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Label = string;
export type DefaultFor = string[];
export type KeyPresent = boolean;
export type PrivacyContract = boolean;
export type ContractReference = string | null;

/**
 * One model engine as the Admin area's System screen shows it (ADR-135 decision 5): its models,
 * the roles it is the default for, and whether its key is present — never the key.
 */
export interface EngineStatus {
  name: Name;
  label: Label;
  models: Models;
  default_for: DefaultFor;
  key_present: KeyPresent;
  privacy_contract?: PrivacyContract;
  contract_reference?: ContractReference;
  [k: string]: unknown;
}
export interface Models {
  [k: string]: string;
}
