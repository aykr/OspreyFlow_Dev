// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Label = string;
export type Roles = ("extraction" | "vision" | "transcription" | "embedding")[];
export type DefaultFor = ("extraction" | "vision" | "transcription" | "embedding")[];
export type PrivacyContract = boolean;
export type Available = boolean;
export type Reason = string | null;

/**
 * An engine an analyst may choose (ADR-135 decision 5): the local engine, and each enabled
 * provider that has a key. Nothing about the key is here, not even whether one exists.
 */
export interface OfferedEngine {
  name: Name;
  label: Label;
  roles: Roles;
  default_for: DefaultFor;
  privacy_contract?: PrivacyContract;
  available?: Available;
  reason?: Reason;
  [k: string]: unknown;
}
